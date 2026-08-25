package handler

import (
	"context"

	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/internal/service"
)

// Context key types for middleware injection.
type contextKey string

const (
	claimsKey contextKey = "user_claims"
)

// GetUserClaims extracts user claims from the request context.
func GetUserClaims(ctx context.Context) (*service.UserClaims, bool) {
	claims, ok := ctx.Value(claimsKey).(*service.UserClaims)
	return claims, ok
}

// SetUserClaims stores user claims in the context.
func SetUserClaims(ctx context.Context, claims *service.UserClaims) context.Context {
	return context.WithValue(ctx, claimsKey, claims)
}
