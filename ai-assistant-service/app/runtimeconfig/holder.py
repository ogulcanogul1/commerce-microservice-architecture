"""Canlı Konfigürasyon Taşıyıcısı (RuntimeConfigHolder).

Bu modül, mikroservisin çalışma anındaki (runtime) aktif konfigürasyonunu bellek
içerisinde güvenli, dondurulmuş (immutable) ve atomik bir şekilde saklar ve yönetir.

Temel Dağıtık Sistem Desenleri ve Çözülen Problemler:
1. Atomik Değiştirme (Atomic Swap):
   Python'ın asyncio event loop yapısında 'self._current = new_settings' ataması
   kesintisiz (atomic) gerçekleşir. İstekler hiçbir zaman kısmi güncellenmiş veya
   yarım bir konfigürasyon göremez.
2. Önce Doğrula, Sonra Değiştir (Validate-Then-Swap):
   Config Server'dan gelen ayarlar derhal canlıya alınmaz. Önce Pydantic model
   doğrulamasından (RuntimeSettings.model_validate) geçer. Eğer bir sınır ihlali
   (örn: timeout > 65s) veya bilinmeyen alan varsa doğrulama patlar; hata loglanır
   ancak aktif 'current' ayara ASLA DOKUNULMAZ. Servis son bilinen iyi konfigürasyon
   (last-known-good) ile kesintisiz hizmet vermeye devam eder.
3. Sürümleme ve Değişiklik Tespiti (Hashing & Diff Logging):
   Konfigürasyonun JSON halinin SHA-256 özeti alınarak 12 haneli bir sürüm hash'i
   üretilir. Config Server'dan aynı ayarlar geldiğinde no-op yapılır (gereksiz log ve
   dinleyici tetiklenmesi önlenir). Değişiklik olduğunda eski ve yeni değerler
   karşılaştırılarak tek satır temiz bir INFO diff logu üretilir.
4. Sabitlenmiş Alanların Korunması (Pinned Overrides):
   Container başlatılırken ortam değişkeni (.env / OS env) ile açıkça verilen ayarlar
   (örn: AGENT_MAX_STEPS=2) 'pinned' kabul edilir. Config Server bu ayar için farklı
   bir değer yayınlasa bile yerel env değeri ezilmez (operatörün yerel müdahale üstünlüğü).
5. Hata İzolasyonu (Failure Isolation):
   Konfigürasyon değişimini dinleyen harici fonksiyonlar (Listeners) bir hata fırlatsa
   dahi bu hata yakalanıp loglanır; swap işlemi geri alınmaz ve diğer dinleyicilerin
   çalışması engellenmez.
"""

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Callable, Literal
from pydantic import ValidationError

from app.runtimeconfig.client import ConfigServerClient, ConfigServerError
from app.runtimeconfig.models import RuntimeSettings
from app.runtimeconfig.parsing import (
    ConfigFormatError,
    extract_runtime_tree,
    merge_property_sources,
)
from app.runtimeconfig.paths import flatten_paths, get_path, set_path

logger = logging.getLogger(__name__)

# Hata türleri: Ağ çekme hatası (fetch), JSON/Property kaynak format hatası (format), Pydantic kural ihlali (validation)
ErrorKind = Literal["fetch", "format", "validation"]

# Konfigürasyon değiştiğinde tetiklenecek geri çağırma fonksiyonu türü: (eski_ayar, yeni_ayar) -> None
Listener = Callable[[RuntimeSettings, RuntimeSettings], None]


def _compute_version(rt: RuntimeSettings) -> str:
    """RuntimeSettings nesnesinin içeriğinden 12 haneli deterministik SHA-256 hash'i üretir.

    Sözlük anahtarları alfabetik sıralanır (sort_keys=True) böylece içerik aynı kaldığı sürece
    her zaman aynı hash elde edilir.
    """
    serialized = json.dumps(rt.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()[:12]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """İki iç içe sözlüğü derinlemesine (recursive) birleştirir.

    Orijinal 'base' sözlüğünü bozmamak için kopyasını alır (immutability).
    Eğer anahtar her iki sözlükte de bir alt sözlükse recursive birleştirilir;
    değilse 'override' içindeki değer 'base' içindekinin üzerine yazar.
    """
    merged = copy.deepcopy(base)
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = copy.deepcopy(v)
    return merged


@dataclass(frozen=True)
class ConfigStatus:
    """Konfigürasyon durumunu ve sağlık metriklerini tutan dondurulmuş veri modeli.

    /health uç noktası bu modeli okuyarak dış dünyaya servis konfigürasyon sağlığını raporlar.
    """

    source: Literal["env", "config-server"]  # Aktif konfigürasyonun kaynağı (env veya config-server)
    version: str                             # 12 haneli SHA-256 sürüm kimliği
    last_success_at: datetime | None         # Son başarılı güncelleme zamanı (UTC)
    last_attempt_at: datetime | None         # Son Config Server yoklama zamanı (UTC)
    consecutive_failures: int                # Art arda yaşanan başarısızlık sayısı (başarıda sıfırlanır)
    last_error: ErrorKind | None             # Karşılaşılan son hata türü
    pinned: tuple[str, ...]                  # Env ile sabitlenmiş ve Config Server'a kapalı alanların listesi


class RuntimeConfigHolder:
    """Canlı konfigürasyon durumunu yöneten ve istek snapshot'larını sağlayan merkez sınıf."""

    def __init__(
        self,
        baseline: RuntimeSettings,
        pinned: frozenset[str],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """RuntimeConfigHolder'ı başlatır.

        Args:
            baseline: Uygulama açılışında kod ve .env değerlerinden türetilmiş temel konfigürasyon.
            pinned: Çevre değişkeni (.env) ile açıkça verilmiş alan adları (örn: {'agent.max_steps'}).
            clock: Testlerde zamanı sabitleyebilmek için opsiyonel saat fonksiyonu (varsayılan: UTC now).
        """
        self._baseline = baseline
        self._pinned = pinned
        self._clock = clock or (lambda: datetime.now(timezone.utc))

        # Başlangıçta aktif konfigürasyon doğrudan baseline'dır
        self._current: RuntimeSettings = baseline
        self._version: str = _compute_version(baseline)
        self._source: Literal["env", "config-server"] = "env"

        # Sağlık ve izlenebilirlik sayaçları
        self._last_success_at: datetime | None = None
        self._last_attempt_at: datetime | None = None
        self._consecutive_failures: int = 0
        self._last_error: ErrorKind | None = None

        # Konfigürasyon güncellendiğinde tetiklenecek dinleyiciler
        self._listeners: list[Listener] = []

    @property
    def current(self) -> RuntimeSettings:
        """O anki aktif ve dondurulmuş RuntimeSettings nesnesini döndürür.

        FastAPI endpoint'leri istek başında bu snapshot'ı bir kez alır ve tur boyunca
        aynı dondurulmuş nesneyi kullanır.
        """
        return self._current

    @property
    def version(self) -> str:
        """Aktif konfigürasyonun 12 karakterlik SHA-256 sürüm karmasını (hash) döner."""
        return self._version

    @property
    def status(self) -> ConfigStatus:
        """/health uç noktası ve gözlemlenebilirlik için mevcut konfigürasyon durumunu döner."""
        return ConfigStatus(
            source=self._source,
            version=self._version,
            last_success_at=self._last_success_at,
            last_attempt_at=self._last_attempt_at,
            consecutive_failures=self._consecutive_failures,
            last_error=self._last_error,
            pinned=tuple(sorted(self._pinned)),
        )

    def add_listener(self, listener: Listener) -> None:
        """Konfigürasyon değiştiğinde haberdar olmak isteyen bir dinleyici (listener) kaydeder."""
        self._listeners.append(listener)

    def apply_property_sources(self, sources: list[dict[str, Any]]) -> bool:
        """Config Server'dan gelen propertySources listesini ayrıştırır, doğrular ve atomik uygular.

        İşlem Adımları:
        1. merge_property_sources + extract_runtime_tree: 'ai.' önekli ayarlar snake_case ağaca çevrilir.
        2. _deep_merge: Baseline üzerine Config Server'dan gelen yeni değerler yazılır.
        3. Pinned Alanların Korunması: Ortam değişkeniyle sabitlenmiş alanlar baseline değerine geri çekilir.
        4. Validate-then-Swap: Yeni konfigürasyon RuntimeSettings ile doğrulanır (hatada istisna fırlatılır).
        5. Hash Kontrolü: Sürüm hash'i aynıysa no-op yapılır (False döner).
        6. Diff Log: Hangi alanların eski -> yeni değer aldığı tek INFO logunda gösterilir.
        7. Atomic Swap: self._current referansı yeni nesneye atanır.
        8. Dinleyiciler: Kayıtlı dinleyiciler try-except korumasında çalıştırılır.

        Returns:
            Konfigürasyon gerçekten değiştiyse True; sürüm aynı kaldıysa False.
        """
        # 1. Adım: Kaynakları birleştir ve sadece 'ai.' alanlarını ağaç yapısına çevir
        tree = extract_runtime_tree(merge_property_sources(sources))
        baseline_dump = self._baseline.model_dump()

        # 2. Adım: Baseline konfigürasyonu temel alıp üzerine Config Server değerlerini yaz
        merged = _deep_merge(baseline_dump, tree)

        # 3. Adım: Env ile sabitlenmiş (pinned) alanları baseline değerine geri sabitle (Env önceliği)
        for path in self._pinned:
            set_path(merged, path, get_path(baseline_dump, path))

        # 4. Adım: Atomik swap öncesinde Pydantic ile sıkı doğrulama (Hatalıysa ValidationError fırlatır)
        new_settings = RuntimeSettings.model_validate(merged)
        new_version = _compute_version(new_settings)

        now = self._clock()
        self._source = "config-server"
        self._last_success_at = now
        self._consecutive_failures = 0
        self._last_error = None

        # 5. Adım: İçerik değişmediyse no-op yap
        if new_version == self._version:
            return False

        # 6. Adım: Eski ve yeni konfigürasyon arasındaki farkları tespit et (Gözlemlenebilirlik / Diff Log)
        old_settings = self._current
        old_flat = flatten_paths(old_settings.model_dump())
        new_flat = flatten_paths(new_settings.model_dump())
        diffs = [
            f"{path} ({old_flat.get(path)} -> {new_flat[path]})"
            for path in new_flat
            if path in old_flat and old_flat[path] != new_flat[path]
        ]
        diff_str = ", ".join(diffs) if diffs else "ayarlar güncellendi"

        # 7. Adım: Atomik Swap (Referans değişimi)
        self._current = new_settings
        old_version = self._version
        self._version = new_version

        logger.info(
            "Runtime config güncellendi (%s -> %s): %s",
            old_version,
            new_version,
            diff_str,
        )

        # 8. Adım: Dinleyicileri haberdar et (Bir dinleyicinin patlaması diğerlerini durdurmaz)
        for listener in self._listeners:
            try:
                listener(old_settings, new_settings)
            except Exception:
                logger.exception("Runtime config dinleyicisi çalışırken beklenmeyen hata oluştu")

        return True

    async def refresh(self, client: ConfigServerClient, app_name: str, profile: str) -> bool:
        """Config Server'a sorgu atarak konfigürasyonu güncellemeyi dener.

        Olası Hata Senaryoları ve Tutumlar:
        - ConfigServerError (Ağ/HTTP 500/Timeout): Hata tipi loglanır, last_error='fetch' yapılır.
        - ConfigFormatError (Bozuk JSON/Placeholder/Liste): Hata loglanır, last_error='format' yapılır.
        - ValidationError (Geçersiz değer, tavan aşımı): include_input=False ile değerler sızdırılmadan
          sadece kural ihlali loglanır, last_error='validation' yapılır.
        - TÜM HATA DURUMLARINDA: 'self._current' asla değiştirilmez; servis eski güvenli config ile çalışır.

        Returns:
            Konfigürasyon başarıyla güncellendiyse True, aksi halde False.
        """
        self._last_attempt_at = self._clock()

        # 1. Aşama: Config Server'dan propertySources listesini çekme
        try:
            sources = await client.fetch_property_sources(app_name, profile)
        except ConfigServerError as exc:
            self._record_failure("fetch")
            logger.warning("Config Server'dan ayarlar çekilemedi: %s", str(exc))
            return False

        # 2. Aşama: Gelen kaynakları doğrulayıp uygulama
        try:
            self.apply_property_sources(sources)
            return True
        except ConfigFormatError as exc:
            self._record_failure("format")
            logger.error("Config Server format hatası: %s", str(exc))
            return False
        except ValidationError as exc:
            self._record_failure("validation")
            # Güvenlik: include_input=False ile loglara kullanıcının girdiği ham değerler değil,
            # yalnızca alan adı (loc) ve doğrulama kuralı (msg) yazılır
            errors = [
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                for err in exc.errors(include_input=False)
            ]
            logger.error("Config Server doğrulama hatası: %s", "; ".join(errors))
            return False

    def _record_failure(self, error_kind: ErrorKind) -> None:
        """Başarısız yoklama istatistiklerini günceller."""
        self._consecutive_failures += 1
        self._last_error = error_kind
