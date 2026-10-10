package com.dgl.product.cqrs.handler.command;

import com.dgl.product.config.RedisConfig;
import com.dgl.product.cqrs.CommandHandler;
import com.dgl.product.cqrs.command.DeleteProductCommand;
import com.dgl.product.domain.Product;
import com.dgl.product.domain.ProductStatus;
import com.dgl.product.exception.ProductNotFoundException;
import com.dgl.product.messaging.event.ProductDeletedPayload;
import com.dgl.product.outbox.OutboxService;
import com.dgl.product.repository.ProductRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class DeleteProductCommandHandler implements CommandHandler<DeleteProductCommand, Void> {

    private final ProductRepository productRepository;
    private final OutboxService outboxService;

    @Override
    @Transactional
    @CacheEvict(value = {RedisConfig.PRODUCTS_CACHE, RedisConfig.PRODUCT_SLUGS_CACHE}, allEntries = true)
    public Void handle(DeleteProductCommand command) {
        UUID id = command.id();
        Product product = productRepository.findById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
        product.setStatus(ProductStatus.ARCHIVED);

        outboxService.recordEvent(
                "Product",
                product.getId().toString(),
                "ProductDeleted",
                UUID.randomUUID(),
                null,
                new ProductDeletedPayload(product.getId(), product.getSku())
        );

        log.info("Product soft-deleted via CQRS: id={}, sku={}", product.getId(), product.getSku());
        return null;
    }
}
