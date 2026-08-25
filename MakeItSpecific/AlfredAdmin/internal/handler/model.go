package handler

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/internal/model"
	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/internal/service"
	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/pkg/response"
)

// ModelHandler handles admin model management endpoints.
type ModelHandler struct {
	modelService *service.ModelService
}

// NewModelHandler creates a new ModelHandler.
func NewModelHandler(modelService *service.ModelService) *ModelHandler {
	return &ModelHandler{modelService: modelService}
}

// RegisterRoutes registers model management routes (admin-only).
func (h *ModelHandler) RegisterRoutes(r chi.Router) {
	r.Post("/models", h.Create)
	r.Get("/models", h.List)
	r.Put("/models/{id}", h.Update)
	r.Delete("/models/{id}", h.Delete)
	r.Put("/models/{id}/toggle", h.Toggle)
	r.Put("/models/{id}/default", h.SetDefault)
}

// Create adds a new model config.
func (h *ModelHandler) Create(w http.ResponseWriter, r *http.Request) {
	var req service.CreateModelRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid request body")
		return
	}

	if req.Alias == "" || req.Provider == "" || req.ModelName == "" || req.BaseURL == "" || req.APIKeyEnvVar == "" {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "All fields are required: alias, provider, model_name, base_url, api_key_env_var")
		return
	}

	m, err := h.modelService.Create(r.Context(), req)
	if err != nil {
		response.WriteError(w, r, http.StatusConflict, "CONFLICT", "Model alias already exists")
		return
	}

	response.WriteJSON(w, http.StatusCreated, map[string]interface{}{"model": m})
}

// List returns all model configs.
func (h *ModelHandler) List(w http.ResponseWriter, r *http.Request) {
	configs, err := h.modelService.List(r.Context())
	if err != nil {
		response.WriteError(w, r, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to list models")
		return
	}
	if configs == nil {
		configs = []model.ModelConfig{} // empty slice, not null
	}
	response.WriteJSON(w, http.StatusOK, map[string]interface{}{"models": configs})
}

// Update modifies a model config.
func (h *ModelHandler) Update(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid model ID")
		return
	}

	var req service.UpdateModelRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid request body")
		return
	}

	m, err := h.modelService.Update(r.Context(), id, req)
	if err != nil {
		response.WriteError(w, r, http.StatusNotFound, "NOT_FOUND", err.Error())
		return
	}

	response.WriteJSON(w, http.StatusOK, map[string]interface{}{"model": m})
}

// Delete removes a model config.
func (h *ModelHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid model ID")
		return
	}

	if err := h.modelService.Delete(r.Context(), id); err != nil {
		code, status := "VALIDATION_ERROR", http.StatusBadRequest
		if err.Error() == "cannot delete the default model — set another model as default first" {
			code, status = "CONFLICT", http.StatusConflict
		}
		response.WriteError(w, r, status, code, err.Error())
		return
	}

	response.WriteJSON(w, http.StatusOK, map[string]string{"message": "model deleted"})
}

// Toggle enables or disables a model.
func (h *ModelHandler) Toggle(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid model ID")
		return
	}

	var req struct {
		Enabled bool `json:"enabled"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid request body")
		return
	}

	if err := h.modelService.Toggle(r.Context(), id, req.Enabled); err != nil {
		response.WriteError(w, r, http.StatusNotFound, "NOT_FOUND", "Model not found")
		return
	}

	status := "disabled"
	if req.Enabled {
		status = "enabled"
	}
	response.WriteJSON(w, http.StatusOK, map[string]string{"message": "model " + status})
}

// SetDefault sets a model as the default.
func (h *ModelHandler) SetDefault(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid model ID")
		return
	}

	if err := h.modelService.SetDefault(r.Context(), id); err != nil {
		response.WriteError(w, r, http.StatusNotFound, "NOT_FOUND", "Model not found")
		return
	}

	response.WriteJSON(w, http.StatusOK, map[string]string{"message": "default model updated"})
}
