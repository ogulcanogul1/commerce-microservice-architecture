package com.dgl.product.cqrs.handler.command;

import com.dgl.product.config.RedisConfig;
import com.dgl.product.cqrs.CommandHandler;
import com.dgl.product.cqrs.command.DeleteCategoryCommand;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.repository.CategoryRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class DeleteCategoryCommandHandler implements CommandHandler<DeleteCategoryCommand, Void> {

    private final CategoryRepository categoryRepository;

    @Override
    @Transactional
    @CacheEvict(value = RedisConfig.CATEGORIES_CACHE, allEntries = true)
    public Void handle(DeleteCategoryCommand command) {
        UUID id = command.id();
        if (!categoryRepository.existsById(id)) {
            throw new CategoryNotFoundException(id);
        }
        categoryRepository.deleteById(id);
        log.info("Category deleted via CQRS: id={}", id);
        return null;
    }
}
