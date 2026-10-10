package com.dgl.customer.cqrs.command;

import com.dgl.customer.cqrs.Command;
import com.dgl.customer.dto.request.UpdatePreferencesRequest;
import com.dgl.customer.dto.response.PreferencesResponse;

import java.util.UUID;

public record UpdatePreferencesCommand(UUID customerId, UpdatePreferencesRequest request) implements Command<PreferencesResponse> {
}
