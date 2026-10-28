package response

import (
	"encoding/json"
	"log/slog"
	"net/http"
)

// ErrorDetail is the unified error structure.
type ErrorDetail struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	RequestID string `json:"request_id"`
}

// ErrorResponse wraps the error detail.
type ErrorResponse struct {
	Error ErrorDetail `json:"error"`
}

// SuccessResponse wraps a successful response.
type SuccessResponse struct {
	Data interface{} `json:"data"`
}

// WriteJSON writes a JSON response with the given status code.
func WriteJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(data); err != nil {
		slog.Error("failed to write JSON response", "error", err)
	}
}

// WriteError writes a unified error response.
func WriteError(w http.ResponseWriter, r *http.Request, status int, code, message string) {
	rid := GetRequestID(r)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(ErrorResponse{
		Error: ErrorDetail{
			Code:      code,
			Message:   message,
			RequestID: rid,
		},
	})
	slog.Warn("request error",
		"request_id", rid,
		"code", code,
		"status", status,
		"message", message,
	)
}

// GetRequestID extracts the request ID from the request context or header.
func GetRequestID(r *http.Request) string {
	// Check context value first
	if rid, ok := r.Context().Value(RequestIDKey).(string); ok && rid != "" {
		return rid
	}
	// Fall back to header
	return r.Header.Get("X-Request-ID")
}

// Context key type for request ID.
type contextKey string

// RequestIDKey is the context key for the request ID.
const RequestIDKey contextKey = "request_id"
