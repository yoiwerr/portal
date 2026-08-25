package handler

import (
	"net/http"

	"github.com/go-chi/chi/v5"

	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/internal/service"
	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/pkg/response"
)

// StatsHandler handles admin statistics endpoints.
type StatsHandler struct {
	statsService *service.StatsService
}

// NewStatsHandler creates a new StatsHandler.
func NewStatsHandler(statsService *service.StatsService) *StatsHandler {
	return &StatsHandler{statsService: statsService}
}

// RegisterRoutes registers stats routes (admin-only).
func (h *StatsHandler) RegisterRoutes(r chi.Router) {
	r.Get("/stats/tokens", h.TokenStats)
	r.Get("/stats/tokens/recent", h.RecentUsage)
	r.Get("/stats/requests", h.RequestStats)
}

// TokenStats returns aggregated token usage statistics.
func (h *StatsHandler) TokenStats(w http.ResponseWriter, r *http.Request) {
	stats, err := h.statsService.GetTokenStats(r.Context())
	if err != nil {
		response.WriteError(w, r, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to get token stats")
		return
	}
	response.WriteJSON(w, http.StatusOK, stats)
}

// RecentUsage returns the most recent model call records.
func (h *StatsHandler) RecentUsage(w http.ResponseWriter, r *http.Request) {
	recent, err := h.statsService.GetRecentUsage(r.Context())
	if err != nil {
		response.WriteError(w, r, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to get recent usage")
		return
	}
	response.WriteJSON(w, http.StatusOK, map[string]interface{}{
		"recent": recent,
	})
}

// RequestStats returns request log statistics.
func (h *StatsHandler) RequestStats(w http.ResponseWriter, r *http.Request) {
	stats, err := h.statsService.GetRequestStats(r.Context())
	if err != nil {
		response.WriteError(w, r, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to get request stats")
		return
	}
	response.WriteJSON(w, http.StatusOK, stats)
}
