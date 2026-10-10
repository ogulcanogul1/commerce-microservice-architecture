package com.dgl.product.cqrs.handler.command;

import com.dgl.product.config.RedisConfig;
import com.dgl.product.cqrs.CommandHandler;
import com.dgl.product.cqrs.command.UpdateProductCommand;
import com.dgl.product.cqrs.mapper.ProductResponseMapper;
import com.dgl.product.domain.Category;
import com.dgl.product.domain.Product;
import com.dgl.product.domain.ProductAttribute;
import com.dgl.product.dto.request.UpdateProductRequest;
import com.dgl.product.dto.response.ProductResponse;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.exception.ProductNotFoundException;
import com.dgl.product.messaging.event.ProductUpdatedPayload;
import com.dgl.product.outbox.OutboxService;
import com.dgl.product.repository.CategoryRepository;
import com.dgl.product.repository.ProductRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class UpdateProductCommandHandler implements CommandHandler<UpdateProductCommand, ProductResponse> {

    private final ProductRepository productRepository;
    private final CategoryRepository categoryRepository;
    private final OutboxService outboxService;
    private final ProductResponseMapper productResponseMapper;

    @Override
    @Transactional
    @CacheEvict(value = {RedisConfig.PRODUCTS_CACHE, RedisConfig.PRODUCT_SLUGS_CACHE}, allEntries = true)
    public ProductResponse handle(UpdateProductCommand command) {
        UUID id = command.id();
        UpdateProductRequest request = command.request();

        Product product = productRepository.findById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));

        Category category = categoryRepository.findById(request.categoryId())
                .orElseThrow(() -> new CategoryNotFoundException(request.categoryId()));

        product.setName(request.name());
        product.setDescription(request.description());
        product.setCategory(category);
        product.setBasePrice(request.basePrice());
        if (request.status() != null) {
            product.setStatus(request.status());
        }

        if (request.attributes() != null) {
            product.getAttributes().clear();
            for (Map.Entry<String, String> entry : request.attributes().entrySet()) {
                ProductAttribute attribute = ProductAttribute.builder()
                        .product(product)
                        .attributeKey(entry.getKey())
                        .attributeValue(entry.getValue())
                        .build();
                product.getAttributes().add(attribute);
            }
        }

        outboxService.recordEvent(
                "Product",
                product.getId().toString(),
                "ProductUpdated",
                UUID.randomUUID(),
                null,
                new ProductUpdatedPayload(
                        product.getId(),
                        product.getSku(),
                        product.getName(),
                        product.getCategory().getId(),
                        product.getBasePrice(),
                        product.getCurrency(),
                        product.getStatus().name()
                )
        );

        log.info("Product updated via CQRS: id={}, sku={}", product.getId(), product.getSku());
        return productResponseMapper.toResponse(product);
    }
}
