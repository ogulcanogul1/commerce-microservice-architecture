package com.dgl.product.repository;

import com.dgl.product.domain.Product;
import com.dgl.product.domain.ProductStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface ProductRepository extends JpaRepository<Product, UUID> {

    Optional<Product> findBySku(String sku);

    Optional<Product> findBySlug(String slug);

    Page<Product> findByCategoryId(UUID categoryId, Pageable pageable);

    Page<Product> findByStatus(ProductStatus status, Pageable pageable);

    boolean existsBySku(String sku);

    boolean existsBySlug(String slug);
}
