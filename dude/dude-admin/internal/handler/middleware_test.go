package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/yoiwerr/portal/dude/dude-admin/internal/service"
)

// Renaming the product must preserve the issuer used by AuthService and existing clients.
func TestAuthPreservesStableIssuer(t *testing.T) {
	secret := "test-only-issuer-regression-secret"
	middleware := NewMiddleware(secret)
	for _, tc := range []struct {
		name, issuer string
		expires      time.Time
		status       int
	}{
		{"stable issuer", "alfred-admin", time.Now().Add(time.Minute), http.StatusNoContent},
		{"renamed issuer rejected", "dude-admin", time.Now().Add(time.Minute), http.StatusUnauthorized},
		{"missing issuer rejected", "", time.Now().Add(time.Minute), http.StatusUnauthorized},
		{"expired rejected", "alfred-admin", time.Now().Add(-time.Minute), http.StatusUnauthorized},
	} {
		t.Run(tc.name, func(t *testing.T) {
			claims := service.UserClaims{
				RegisteredClaims: jwt.RegisteredClaims{
					Issuer:    tc.issuer,
					ExpiresAt: jwt.NewNumericDate(tc.expires),
				},
				UserID: "regression-user", Username: "regression", Role: "user",
			}
			token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(secret))
			if err != nil {
				t.Fatal(err)
			}
			request := httptest.NewRequest(http.MethodGet, "/api/v1/auth/me", nil)
			request.Header.Set("Authorization", "Bearer "+token)
			recorder := httptest.NewRecorder()
			middleware.Auth(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				got, ok := GetUserClaims(r.Context())
				if !ok || got.UserID != claims.UserID {
					t.Fatal("claims were not passed to handler")
				}
				w.WriteHeader(http.StatusNoContent)
			})).ServeHTTP(recorder, request)
			if recorder.Code != tc.status {
				t.Fatalf("got %d, want %d", recorder.Code, tc.status)
			}
		})
	}
}
