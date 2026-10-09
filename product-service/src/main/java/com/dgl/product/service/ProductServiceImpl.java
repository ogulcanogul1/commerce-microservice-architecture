package com.dgl.product.service;

import com.dgl.product.domain.Category;
import com.dgl.product.domain.Product;
import com.dgl.product.domain.ProductAttribute;
import com.dgl.product.domain.ProductStatus;
import com.dgl.product.dto.request.CreateProductRequest;
import com.dgl.product.dto.request.UpdateProductRequest;
import com.dgl.product.dto.response.ProductResponse;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.exception.ProductAlreadyExistsException;
import com.dgl.product.exception.ProductNotFoundException;
import com.dgl.product.messaging.event.ProductCreatedPayload;
import com.dgl.product.messaging.event.ProductDeletedPayload;
import com.dgl.product.messaging.event.ProductUpdatedPayload;
import com.dgl.product.outbox.OutboxService;
import com.dgl.product.repository.CategoryRepository;
import com.dgl.product.repository.ProductRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.dgl.product.config.RedisConfig;

import java.text.Normalizer;
import java.util.*;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ProductServiceImpl implements ProductService {

    private static final Pattern NONLATIN = Pattern.compile("[^\\w-]");
    private static final Pattern WHITESPACE = Pattern.compile("[\\s]");

    private final ProductRepository productRepository;
    private final CategoryRepository categoryRepository;
    private final OutboxService outboxService;

    @Override
    @Transactional
    @CacheEvict(value = {RedisConfig.PRODUCTS_CACHE, RedisConfig.PRODUCT_SLUGS_CACHE}, allEntries = true)
    public ProductResponse createProduct(CreateProductRequest request) {
        if (productRepository.existsBySku(request.sku())) {
            throw new ProductAlreadyExistsException("Product with SKU '" + request.sku() + "' already exists");
        }

        Category category = categoryRepository.findById(request.categoryId())
                .orElseThrow(() -> new CategoryNotFoundException(request.categoryId()));

        String slug = toSlug(request.name());
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

        return mapToResponse(savedProduct);
    }

    @Override
    @Transactional
    @CacheEvict(value = {RedisConfig.PRODUCTS_CACHE, RedisConfig.PRODUCT_SLUGS_CACHE}, allEntries = true)
    public ProductResponse updateProduct(UUID id, UpdateProductRequest request) {
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

        return mapToResponse(product);
    }

    @Override
    @Cacheable(value = RedisConfig.PRODUCTS_CACHE, key = "#id")
    public ProductResponse getProductById(UUID id) {
        Product product = productRepository.findById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
        return mapToResponse(product);
    }

    @Override
    @Cacheable(value = RedisConfig.PRODUCTS_CACHE, key = "#sku")
    public ProductResponse getProductBySku(String sku) {
        Product product = productRepository.findBySku(sku)
                .orElseThrow(() -> new ProductNotFoundException("Product not found with SKU: " + sku));
        return mapToResponse(product);
    }

    @Override
    @Cacheable(value = RedisConfig.PRODUCT_SLUGS_CACHE, key = "#slug")
    public ProductResponse getProductBySlug(String slug) {
        Product product = productRepository.findBySlug(slug)
                .orElseThrow(() -> new ProductNotFoundException("Product not found with slug: " + slug));
        return mapToResponse(product);
    }

    @Override
    public Page<ProductResponse> getAllProducts(Pageable pageable) {
        return productRepository.findAll(pageable)
                .map(this::mapToResponse);
    }

    @Override
    public Page<ProductResponse> getProductsByCategory(UUID categoryId, Pageable pageable) {
        if (!categoryRepository.existsById(categoryId)) {
            throw new CategoryNotFoundException(categoryId);
        }
        return productRepository.findByCategoryId(categoryId, pageable)
                .map(this::mapToResponse);
    }

    @Override
    @Transactional
    @CacheEvict(value = {RedisConfig.PRODUCTS_CACHE, RedisConfig.PRODUCT_SLUGS_CACHE}, allEntries = true)
    public void deleteProduct(UUID id) {
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
    }

    private ProductResponse mapToResponse(Product product) {
        Map<String, String> attributesMap = product.getAttributes() != null
                ? product.getAttributes().stream()
                .collect(Collectors.toMap(
                        ProductAttribute::getAttributeKey,
                        ProductAttribute::getAttributeValue,
                        (existing, replacement) -> replacement))
                : Collections.emptyMap();

        return new ProductResponse(
                product.getId(),
                product.getSku(),
                product.getName(),
                product.getSlug(),
                product.getDescription(),
                product.getCategory() != null ? product.getCategory().getId() : null,
                product.getCategory() != null ? product.getCategory().getName() : null,
                product.getBasePrice(),
                product.getCurrency(),
                product.getStatus(),
                attributesMap,
                product.getCreatedAt(),
                product.getUpdatedAt()
        );
    }

    private String toSlug(String input) {
        String nowhitespace = WHITESPACE.matcher(input.trim().toLowerCase(Locale.ENGLISH)).replaceAll("-");
        String normalized = Normalizer.normalize(nowhitespace, Normalizer.Form.NFD);
        String slug = NONLATIN.matcher(normalized).replaceAll("");
        return slug.replaceAll("-+", "-");
    }
}
