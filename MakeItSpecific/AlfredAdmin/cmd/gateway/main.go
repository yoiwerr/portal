package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	chiMiddleware "github.com/go-chi/chi/v5/middleware"

	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/config"
	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/internal/handler"
	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/internal/service"
	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/internal/store"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})))

	cfg := config.Load()

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// ── PostgreSQL ──
	slog.Info("connecting to PostgreSQL...")
	pg, err := store.NewPostgres(ctx, cfg.DatabaseURL)
	if err != nil {
		slog.Error("failed to connect to PostgreSQL", "error", err)
		os.Exit(1)
	}
	defer pg.Close()

	// Run migrations
	if err := pg.RunMigrations(ctx, "migrations"); err != nil {
		slog.Error("failed to run migrations", "error", err)
		os.Exit(1)
	}

	// ── Business services ──
	authService := service.NewAuthService(
		pg.Pool,
		cfg.JWTSecret,
		cfg.JWTAccessExpiry,
		cfg.JWTRefreshExpiry,
		cfg.AdminInitPassword,
	)
	modelService := service.NewModelService(pg.Pool)
	statsService := service.NewStatsService(pg.Pool)

	// ── Seed data ──
	if err := authService.SeedAdmin(ctx); err != nil {
		slog.Warn("failed to seed admin user", "error", err)
	}
	if err := modelService.SeedDefault(ctx); err != nil {
		slog.Warn("failed to seed default model", "error", err)
	}

	// ── Middleware ──
	mw := handler.NewMiddleware(cfg.JWTSecret)

	// ── Handlers ──
	authHandler := handler.NewAuthHandler(authService)
	modelHandler := handler.NewModelHandler(modelService)
	statsHandler := handler.NewStatsHandler(statsService)

	// ── Router ──
	r := chi.NewRouter()

	// Global middleware
	r.Use(chiMiddleware.RealIP)
	r.Use(chiMiddleware.Recoverer)
	r.Use(mw.RequestID)
	r.Use(mw.Logging)

	// Health check
	r.Get("/api/v1/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"ok","service":"alfred-admin"}`))
	})

	// ── Static files (login + admin pages) ──
	staticFS := http.FileServer(http.Dir("static"))
	r.Handle("/static/*", http.StripPrefix("/static/", staticFS))

	// Convenience: /auth/ → login page
	r.Get("/auth/", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "static/login.html")
	})
	r.Get("/auth", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/auth/", http.StatusMovedPermanently)
	})

	// Convenience: /admin/ → admin page
	r.Get("/admin/", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "static/admin.html")
	})
	r.Get("/admin", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/admin/", http.StatusMovedPermanently)
	})

	// ── API v1 ──
	r.Route("/api/v1", func(r chi.Router) {

		// Public auth routes (no JWT required)
		r.Post("/auth/register", authHandler.Register)
		r.Post("/auth/login", authHandler.Login)
		r.Post("/auth/refresh", authHandler.Refresh)

		// Authenticated auth routes (JWT required)
		r.Group(func(r chi.Router) {
			r.Use(mw.Auth)
			r.Post("/auth/logout", authHandler.Logout)
			r.Get("/auth/me", authHandler.Me)
		})

		// Admin-only routes (JWT + admin role required)
		r.Route("/admin", func(r chi.Router) {
			r.Use(mw.Auth)
			r.Use(mw.AdminOnly)

			modelHandler.RegisterRoutes(r)
			statsHandler.RegisterRoutes(r)
		})
	})

	// ── Server ──
	addr := fmt.Sprintf(":%s", cfg.Port)
	srv := &http.Server{
		Addr:         addr,
		Handler:      r,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh
		slog.Info("shutting down...")
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer shutdownCancel()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			slog.Error("shutdown error", "error", err)
		}
	}()

	slog.Info("Admin starting", "port", cfg.Port)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		slog.Error("server error", "error", err)
		os.Exit(1)
	}

	slog.Info("Admin stopped")
}
