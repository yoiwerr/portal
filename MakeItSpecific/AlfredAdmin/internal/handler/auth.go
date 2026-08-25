package handler

import (
	"encoding/json"
	"net/http"

	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/internal/service"
	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/pkg/response"
)

// AuthHandler handles authentication endpoints.
type AuthHandler struct {
	authService *service.AuthService
}

// NewAuthHandler creates a new AuthHandler.
func NewAuthHandler(authService *service.AuthService) *AuthHandler {
	return &AuthHandler{authService: authService}
}

// Register handles user registration.
func (h *AuthHandler) Register(w http.ResponseWriter, r *http.Request) {
	var req service.RegisterRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid request body")
		return
	}

	user, err := h.authService.Register(r.Context(), req)
	if err != nil {
		if err.Error() == "username already exists" {
			response.WriteError(w, r, http.StatusConflict, "CONFLICT", err.Error())
			return
		}
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", err.Error())
		return
	}

	response.WriteJSON(w, http.StatusCreated, map[string]interface{}{
		"user": user,
	})
}

// Login handles user login.
func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	var req service.LoginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid request body")
		return
	}

	pair, err := h.authService.Login(r.Context(), req)
	if err != nil {
		response.WriteError(w, r, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		return
	}

	response.WriteJSON(w, http.StatusOK, pair)
}

// Refresh handles token refresh.
func (h *AuthHandler) Refresh(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RefreshToken string `json:"refresh_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid request body")
		return
	}
	if req.RefreshToken == "" {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "refresh_token is required")
		return
	}

	pair, err := h.authService.RefreshAccessToken(r.Context(), req.RefreshToken)
	if err != nil {
		response.WriteError(w, r, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		return
	}

	response.WriteJSON(w, http.StatusOK, pair)
}

// Logout invalidates the refresh token.
func (h *AuthHandler) Logout(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RefreshToken string `json:"refresh_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid request body")
		return
	}

	if err := h.authService.Logout(r.Context(), req.RefreshToken); err != nil {
		response.WriteError(w, r, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to logout")
		return
	}

	response.WriteJSON(w, http.StatusOK, map[string]string{"message": "logged out"})
}

// Me returns the current user's info.
func (h *AuthHandler) Me(w http.ResponseWriter, r *http.Request) {
	claims, ok := GetUserClaims(r.Context())
	if !ok {
		response.WriteError(w, r, http.StatusUnauthorized, "UNAUTHORIZED", "Not authenticated")
		return
	}

	response.WriteJSON(w, http.StatusOK, map[string]interface{}{
		"user_id":  claims.UserID,
		"username": claims.Username,
		"role":     claims.Role,
	})
}
