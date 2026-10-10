package com.dgl.product.cqrs.handler.command;

import com.dgl.product.config.RedisConfig;
import com.dgl.product.cqrs.CommandHandler;
import com.dgl.product.cqrs.command.CreateProductCommand;
import com.dgl.product.cqrs.mapper.ProductResponseMapper;
import com.dgl.product.cqrs.util.SlugUtils;
import com.dgl.product.domain.Category;
import com.dgl.product.domain.Product;
import com.dgl.product.domain.ProductAttribute;
import com.dgl.product.domain.ProductStatus;
import com.dgl.product.dto.request.CreateProductRequest;
import com.dgl.product.dto.response.ProductResponse;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.exception.ProductAlreadyExistsException;
import com.dgl.product.messaging.event.ProductCreatedPayload;
import com.dgl.product.outbox.OutboxService;
import com.dgl.product.repository.CategoryRepository;
import com.dgl.product.repository.ProductRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class CreateProductCommandHandler implements CommandHandler<CreateProductCommand, ProductResponse> {

    private final ProductRepository productRepository;
    private final CategoryRepository categoryRepository;
    private final OutboxService outboxService;
    private final ProductResponseMapper productResponseMapper;

    @Override
    @Transactional
    @CacheEvict(value = {RedisConfig.PRODUCTS_CACHE, RedisConfig.PRODUCT_SLUGS_CACHE}, allEntries = true)
    public ProductResponse handle(CreateProductCommand command) {
        CreateProductRequest request = command.request();

        if (productRepository.existsBySku(request.sku())) {
            throw new ProductAlreadyExistsException("Product with SKU '" + request.sku() + "' already exists");
        }

        Category category = categoryRepository.findById(request.categoryId())
                .orElseThrow(() -> new CategoryNotFoundException(request.categoryId()));

        String slug = SlugUtils.toSlug(request.name());
        if (productRepository.existsBySlug(slug)) {
            slug = slug + "-" + UUID.randomUUID().toString().substring(0, 8);
        }

        Product product = Product.builder()
                .sku(request.sku())
                .name(request.name())
                .slug(slug)
                .description(request.description())
                .category(category)
                .basePrice(request.basePrice())
                .currency(request.currency() != null ? request.currency() : "TRY")
                .status(ProductStatus.ACTIVE)
                .attributes(new ArrayList<>())
                .build();

        if (request.attributes() != null && !request.attributes().isEmpty()) {
            for (Map.Entry<String, String> entry : request.attributes().entrySet()) {
                ProductAttribute attribute = ProductAttribute.builder()
                        .product(product)
                        .attributeKey(entry.getKey())
                        .attributeValue(entry.getValue())
                        .build();
                product.getAttributes().add(attribute);
            }
        }

        Product savedProduct = productRepository.save(product);

        outboxService.recordEvent(
                "Product",
                savedProduct.getId().toString(),
                "ProductCreated",
                UUID.randomUUID(),
                null,
                new ProductCreatedPayload(
                        savedProduct.getId(),
                        savedProduct.getSku(),
                        savedProduct.getName(),
                        savedProduct.getSlug(),
                        savedProduct.getCategory().getId(),
                        savedProduct.getBasePrice(),
                        savedProduct.getCurrency(),
                        savedProduct.getStatus().name()
                )
        );

        log.info("Product created successfully via CQRS: id={}, sku={}", savedProduct.getId(), savedProduct.getSku());
        return productResponseMapper.toResponse(savedProduct);
    }
}
