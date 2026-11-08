"""Eureka Service Registry yaşam döngüsü ve arka plan nabız (heartbeat) yöneticisi."""

import asyncio
import logging

from app.discovery.client import EurekaClient, EurekaError
from app.discovery.models import InstanceInfo

logger = logging.getLogger(__name__)


class EurekaRegistrar:
    """Eureka kayıt ve arka plan nabız (heartbeat) döngüsünü yöneten orkestratör sınıf.

    MİMARİ SORUMLULUKLARI:
    1. İlk Kayıt (Resilient Startup):
       Uygulama açılırken Eureka'ya ilk 'POST /apps' isteğini atar.
       Eğer Eureka o an kapalıysa uygulamanın çökmesini engeller (fail-open) ve
       arka plan döngüsünü yine de başlatarak Eureka ayağa kalktığında otomatik kaydolmasını sağlar.

    2. Nabız Döngüsü (Heartbeat & 404 Recovery):
       Eureka, her 10 saniyede bir (renewal_sec) 'PUT /apps/{app}/{id}?status=UP' nabzı bekler.
       Eğer 30 saniye (lease_sec) boyunca nabız gitmezse veya Eureka sunucusu restart edilirse
       Eureka servisi belleğinden siler ve nabız isteğine '404 Not Found' döner.
       Bu sınıf 404 yanıtını yakalar ve servisi baştan 'register' ederek kendini kurtarır.

    3. Zarif Çekilme (Graceful Drain & Idempotency):
       Uygulama kapanırken sırasıyla:
       a) Heartbeat döngüsünü hemen keser.
       b) Servisi Eureka'da 'OUT_OF_SERVICE' yapar (Gateway yeni istek yönlendirmeyi kessin).
       c) Eureka'daki instance kaydını siler (deregister).
       'self._drained' bayrağı ile bu işlemin birden fazla kez çalıştırılması (SIGTERM + Lifespan)
       engellenir (idempotency).
    """

    def __init__(
        self,
        client: EurekaClient,
        info: InstanceInfo,
        renewal_sec: int = 10,
        drain_sec: int = 20,
    ) -> None:
        """Registrar bileşenini hazırlar.

        Args:
            client: Eureka REST API çağrılarını yapan HTTP istemcisi.
            info: Eureka'ya bildirilen servisin IP, port ve meta veri modeli.
            renewal_sec: Nabız gönderme sıklığı (saniye, varsayılan 10).
            drain_sec: Kapanışta Gateway önbelleklerinin boşalması için beklenecek süre (saniye, varsayılan 20).
        """
        self.client = client
        self.info = info
        self.renewal_sec = renewal_sec
        self.drain_sec = drain_sec

        # Servisin kapanma emri alıp almadığını kontrol eden thread-safe asenkron bayrak
        self._stopping = asyncio.Event()

        # Arka planda döngüyü yürüten bağımsız asyncio görevi (Task)
        self._heartbeat_task: asyncio.Task[None] | None = None

        # Çift kapanış çağrısını (örn: hem SIGTERM yakalayıcı hem lifespan) önleyen idempotency kilidi
        self._drained = False

    async def start(self) -> None:
        """Eureka'ya ilk kaydı dener ve arka plan nabız görevini başlatır.

        NEDEN HATA FIRLATMIYORUZ? (Fail-Open Başlangıç):
        Dağıtık sistemlerde mikroservislerin başlangıç sırası garanti edilemez.
        Eğer Eureka sunucusu o an yeniden başlatılıyorsa veya ağda 2 saniyelik bir gecikme varsa,
        bu servisin ayağa kalkmayı reddedip çökmesi (CrashLoopBackOff) istenmeyen bir durumdur.
        İlk kayıt patlasa bile 'warning' loglayıp arka plan döngüsünü başlatıyoruz.
        Eureka hazır olduğunda ilk periyotta zaten kayıt başarıyla gerçekleşecektir.
        """
        try:
            await self.client.register(self.info)
            logger.info("Eureka servisine basariyla kaydolundu (instance: %s)", self.info.instance_id)
        except EurekaError as exc:
            # Hata detayını loglara taşırken sadece istisna sınıfı adını basıyoruz (güvenlik kuralı)
            logger.warning(
                "Eureka ilk kayit basarisiz oldu, heartbeat dongusu yeniden deneyecek: %s",
                type(exc).__name__,
            )

        # Arka plan görevini (coroutine) ana döngüyü bloklamadan bağımsız bir task olarak fırlatıyoruz
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        """Servis hayatta olduğu sürece belirlenen periyotta Eureka'ya nabız gönderen döngü."""
        while not self._stopping.is_set():
            try:
                # KRİTİK TASARIM: 'asyncio.sleep(self.renewal_sec)' KULLANMIYORUZ!
                # Neden? Eğer sleep(10) deseydik ve 1. saniyede servise 'kapan' emri gelseydi,
                # servis kapanmak için kalan 9 saniyenin bitmesini beklemek zorunda kalırdı.
                # 'asyncio.wait_for(self._stopping.wait(), timeout=...)' kullandığımızda:
                # - Normalde 10 saniye bekler ve TimeoutError fırlatarak aşağıdaki koda geçer.
                # - Ama eğer 'self._stopping.set()' çağrılırsa 10 saniyeyi beklemeden O MİLİSANİYEDE uyanır!
                await asyncio.wait_for(self._stopping.wait(), timeout=self.renewal_sec)
                # Buraya düştüyse '_stopping' sinyali gelmiştir; döngüyü hemen kırıp çıkıyoruz
                break
            except asyncio.TimeoutError:
                # Beklenen süre doldu, yani nabız zamanı geldi, döngü devam ediyor
                pass

            # Uyanma anında durdurma sinyali geldiyse gereksiz nabız atmamak için tekrar kontrol
            if self._stopping.is_set():
                break

            try:
                # Eureka'ya "Ben buradayım, durumum UP" de
                alive = await self.client.heartbeat(self.info)

                if not alive:
                    # alive == False demek Eureka bize '404 Not Found' döndü demektir!
                    # Bu ne anlama gelir? Eureka sunucusu belleğini sıfırlamış veya kiralama süremiz dolmuş.
                    # Bu bir kriz değildir; hemen 'register' çağırarak kendimizi sıfırdan kaydettiriyoruz.
                    logger.warning(
                        "Eureka heartbeat 404 dondu (kayit silinmis), yeniden kaydolunuyor: %s",
                        self.info.instance_id,
                    )
                    await self.client.register(self.info)

            except EurekaError as exc:
                # Ağ kopması, Eureka'nın 500 dönmesi veya anlık DNS gecikmelerinde:
                # ASLA döngüyü öldürmüyoruz! Sadece uyarı loglayıp bir sonraki turu bekliyoruz.
                logger.warning("Eureka heartbeat hatasi: %s", type(exc).__name__)
            except Exception:
                # Programlama hatası veya beklenmeyen sistemik istisnalarda dahi döngü canlı kalmalıdır.
                logger.exception("Eureka heartbeat dongusunde beklenmeyen hata olustu")

    async def drain_and_deregister(self) -> None:
        """Kapanış sırasında servisi sırasıyla durdurur, OUT_OF_SERVICE yapar ve kaydı siler.

        NEDEN BURADA 'drain_sec' KADAR BEKLEMİYORUZ?
        Çünkü bekleme işlemi soketin açık kalmasını gerektirir ve bu mantık 'drain.py' içindeki
        sinyal işleyicisine aittir. Bu metot yalnızca Eureka üzerindeki durumu atomik olarak günceller.
        """
        # İdempotency Kontrolü: Bu fonksiyon bir kez çalıştıktan sonra tekrar çağrılırsa no-op (etkisiz) olur.
        if self._drained:
            return
        self._drained = True

        # ADIM 1: Heartbeat döngüsünü durdur
        self._stopping.set()
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                # Görev iptal edildiğinde CancelledError fırlatılması beklenen doğal bir davranıştır
                pass

        # ADIM 2: Durumu 'OUT_OF_SERVICE' yap
        # Neden? Gateway servisin öldüğünü henüz bilmese bile bu statüyü gördüğü an
        # yeni kullanıcı isteklerini bu instance'a yönlendirmeyi anında keser.
        try:
            await self.client.set_status(self.info, "OUT_OF_SERVICE")
            logger.info("Eureka instance durumu OUT_OF_SERVICE olarak guncellendi")
        except EurekaError as exc:
            # Durum güncellenemese bile bir sonraki 'deregister' adımını engellemiyoruz
            logger.warning("Eureka OUT_OF_SERVICE guncelleme basarisiz: %s", type(exc).__name__)

        # ADIM 3: Kaydı Eureka'dan tamamen sil (deregister)
        # Eureka sunucusuna DELETE isteği atarak kendimizi listeden tamamen sildiriyoruz.
        try:
            await self.client.deregister(self.info)
            logger.info("Eureka kaydi basariyla silindi (deregister)")
        except EurekaError as exc:
            logger.warning("Eureka deregister basarisiz: %s", type(exc).__name__)

    async def stop(self) -> None:
        """Tüm yaşam döngüsünü güvenli biçimde sonlandırır.

        Lifespan kapanışında veya uygulama kapatılırken çağrılır.
        Önce drain ve deregister adımlarını tamamlar, ardından HTTP oturumunu (bağlantı havuzunu) kapatır.
        """
        await self.drain_and_deregister()
        await self.client.aclose()
