package service

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/crypto/bcrypt"

	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/internal/model"
)

// AuthService handles authentication business logic.
// Refresh tokens are stored in PostgreSQL (no Redis dependency).
type AuthService struct {
	db            *pgxpool.Pool
	jwtSecret     []byte
	accessExpiry  time.Duration
	refreshExpiry time.Duration
	adminInitPwd  string
}

// NewAuthService creates a new AuthService.
func NewAuthService(db *pgxpool.Pool, jwtSecret string, accessExpiry, refreshExpiry time.Duration, adminInitPwd string) *AuthService {
	return &AuthService{
		db:            db,
		jwtSecret:     []byte(jwtSecret),
		accessExpiry:  accessExpiry,
		refreshExpiry: refreshExpiry,
		adminInitPwd:  adminInitPwd,
	}
}

// RegisterRequest is the request body for user registration.
type RegisterRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// LoginRequest is the request body for login.
type LoginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// TokenPair contains access and refresh tokens.
type TokenPair struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int64  `json:"expires_in"`
}

// UserClaims are the JWT claims.
type UserClaims struct {
	jwt.RegisteredClaims
	UserID   string `json:"user_id"`
	Username string `json:"username"`
	Role     string `json:"role"`
}

// Register creates a new user account.
func (s *AuthService) Register(ctx context.Context, req RegisterRequest) (*model.User, error) {
	if len(req.Username) < 3 || len(req.Username) > 64 {
		return nil, fmt.Errorf("username must be 3-64 characters")
	}
	if len(req.Password) < 6 {
		return nil, fmt.Errorf("password must be at least 6 characters")
	}

	hash, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		return nil, fmt.Errorf("hash password: %w", err)
	}

	var user model.User
	err = s.db.QueryRow(ctx,
		`INSERT INTO admin_users (username, password_hash, role) VALUES ($1, $2, 'user')
		 RETURNING id, username, password_hash, role, is_active, created_at, updated_at`,
		req.Username, string(hash),
	).Scan(&user.ID, &user.Username, &user.PasswordHash, &user.Role, &user.IsActive, &user.CreatedAt, &user.UpdatedAt)
	if err != nil {
		if isUniqueViolation(err) {
			return nil, fmt.Errorf("username already exists")
		}
		return nil, fmt.Errorf("create user: %w", err)
	}

	return &user, nil
}

// Login authenticates a user and returns a token pair.
func (s *AuthService) Login(ctx context.Context, req LoginRequest) (*TokenPair, error) {
	var user model.User
	err := s.db.QueryRow(ctx,
		`SELECT id, username, password_hash, role, is_active FROM admin_users WHERE username = $1`,
		req.Username,
	).Scan(&user.ID, &user.Username, &user.PasswordHash, &user.Role, &user.IsActive)
	if err != nil {
		if err == pgx.ErrNoRows {
			return nil, fmt.Errorf("invalid username or password")
		}
		return nil, fmt.Errorf("query user: %w", err)
	}

	if !user.IsActive {
		return nil, fmt.Errorf("account is disabled")
	}

	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(req.Password)); err != nil {
		return nil, fmt.Errorf("invalid username or password")
	}

	return s.generateTokenPair(ctx, user)
}

// RefreshAccessToken validates a refresh token and returns a new token pair.
func (s *AuthService) RefreshAccessToken(ctx context.Context, refreshToken string) (*TokenPair, error) {
	tokenHash := hashToken(refreshToken)

	var userID string
	var revoked bool
	err := s.db.QueryRow(ctx,
		`SELECT user_id, revoked FROM admin_refresh_tokens WHERE token_hash = $1 AND expires_at > NOW()`,
		tokenHash,
	).Scan(&userID, &revoked)
	if err != nil {
		return nil, fmt.Errorf("invalid or expired refresh token")
	}
	if revoked {
		return nil, fmt.Errorf("refresh token has been revoked")
	}

	uid, err := uuid.Parse(userID)
	if err != nil {
		return nil, fmt.Errorf("invalid user ID in token")
	}

	var user model.User
	err = s.db.QueryRow(ctx,
		`SELECT id, username, password_hash, role, is_active FROM admin_users WHERE id = $1 AND is_active = true`,
		uid,
	).Scan(&user.ID, &user.Username, &user.PasswordHash, &user.Role, &user.IsActive)
	if err != nil {
		return nil, fmt.Errorf("user not found or disabled")
	}

	// Rotate: revoke old refresh token
	_, _ = s.db.Exec(ctx, `UPDATE admin_refresh_tokens SET revoked = true WHERE token_hash = $1`, tokenHash)

	return s.generateTokenPair(ctx, user)
}

// Logout invalidates the refresh token.
func (s *AuthService) Logout(ctx context.Context, refreshToken string) error {
	tokenHash := hashToken(refreshToken)
	_, err := s.db.Exec(ctx, `UPDATE admin_refresh_tokens SET revoked = true WHERE token_hash = $1`, tokenHash)
	return err
}

// GetUserByID retrieves a user by ID.
func (s *AuthService) GetUserByID(ctx context.Context, id uuid.UUID) (*model.User, error) {
	var user model.User
	err := s.db.QueryRow(ctx,
		`SELECT id, username, password_hash, role, is_active, created_at, updated_at FROM admin_users WHERE id = $1`,
		id,
	).Scan(&user.ID, &user.Username, &user.PasswordHash, &user.Role, &user.IsActive, &user.CreatedAt, &user.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return &user, nil
}

// SeedAdmin creates the default admin user if it doesn't exist.
func (s *AuthService) SeedAdmin(ctx context.Context) error {
	var count int
	err := s.db.QueryRow(ctx, `SELECT COUNT(*) FROM admin_users WHERE role = 'admin'`).Scan(&count)
	if err != nil {
		return err
	}
	if count > 0 {
		return nil
	}

	hash, err := bcrypt.GenerateFromPassword([]byte(s.adminInitPwd), bcrypt.DefaultCost)
	if err != nil {
		return err
	}

	_, err = s.db.Exec(ctx,
		`INSERT INTO admin_users (username, password_hash, role) VALUES ('admin', $1, 'admin')`,
		string(hash),
	)
	return err
}

// generateTokenPair creates a new access + refresh token pair.
func (s *AuthService) generateTokenPair(ctx context.Context, user model.User) (*TokenPair, error) {
	now := time.Now()
	accessExp := now.Add(s.accessExpiry)

	claims := UserClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:    "alfred-admin",
			Subject:   user.ID.String(),
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(accessExp),
			ID:        uuid.New().String(),
		},
		UserID:   user.ID.String(),
		Username: user.Username,
		Role:     user.Role,
	}

	accessToken, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString(s.jwtSecret)
	if err != nil {
		return nil, fmt.Errorf("sign access token: %w", err)
	}

	refreshToken := uuid.New().String() + "-" + uuid.New().String()
	tokenHash := hashToken(refreshToken)
	expiresAt := now.Add(s.refreshExpiry)

	_, err = s.db.Exec(ctx,
		`INSERT INTO admin_refresh_tokens (user_id, token_hash, expires_at) VALUES ($1, $2, $3)`,
		user.ID.String(), tokenHash, expiresAt,
	)
	if err != nil {
		return nil, fmt.Errorf("store refresh token: %w", err)
	}

	return &TokenPair{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		TokenType:    "Bearer",
		ExpiresIn:    int64(s.accessExpiry.Seconds()),
	}, nil
}

// hashToken creates a SHA-256 hash of a token string.
func hashToken(token string) string {
	h := sha256.Sum256([]byte(token))
	return hex.EncodeToString(h[:])
}

func isUniqueViolation(err error) bool {
	if err == nil {
		return false
	}
	msg := err.Error()
	return strings.Contains(msg, "unique") || strings.Contains(msg, "duplicate")
}
