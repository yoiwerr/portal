package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/yoiwerr/portal/dude/dude-admin/internal/service"
)

const testSecret = "isolated-test-secret-at-least-32-characters"

func signedToken(t *testing.T, role string, method jwt.SigningMethod, expiry time.Time) string {
	t.Helper()
	claims := service.UserClaims{UserID: uuid.NewString(), Username: "test", Role: role,
		RegisteredClaims: jwt.RegisteredClaims{Issuer: "alfred-admin", ExpiresAt: jwt.NewNumericDate(expiry)}}
	token, err := jwt.NewWithClaims(method, claims).SignedString([]byte(testSecret))
	if err != nil {
		t.Fatal(err)
	}
	return token
}

func TestAdminPermissions(t *testing.T) {
	mw := NewMiddleware(testSecret)
	reached := false
	h := mw.Auth(mw.AdminOnly(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { reached = true; w.WriteHeader(200) })))
	for _, test := range []struct {
		name, token string
		status      int
	}{
		{"anonymous", "", 401},
		{"user", signedToken(t, "user", jwt.SigningMethodHS256, time.Now().Add(time.Hour)), 403},
		{"admin", signedToken(t, "admin", jwt.SigningMethodHS256, time.Now().Add(time.Hour)), 200},
		{"expired admin", signedToken(t, "admin", jwt.SigningMethodHS256, time.Now().Add(-time.Hour)), 401},
		{"wrong algorithm", signedToken(t, "admin", jwt.SigningMethodHS384, time.Now().Add(time.Hour)), 401},
		{"forged", "eyJhbGciOiJub25lIn0.eyJyb2xlIjoiYWRtaW4ifQ.", 401},
	} {
		t.Run(test.name, func(t *testing.T) {
			reached = false
			r := httptest.NewRequest("GET", "/admin/users", nil)
			if test.token != "" {
				r.Header.Set("Authorization", "Bearer "+test.token)
			}
			w := httptest.NewRecorder()
			h.ServeHTTP(w, r)
			if w.Code != test.status || reached != (test.status == 200) {
				t.Fatalf("status=%d reached=%v", w.Code, reached)
			}
		})
	}
}

// Each run uses a fresh schema in an explicitly named disposable database.
func TestUserDirectoryPostgres(t *testing.T) {
	dsn := os.Getenv("ALFRED_ADMIN_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("ALFRED_ADMIN_TEST_DATABASE_URL is not configured")
	}
	ctx := context.Background()
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(cfg.ConnConfig.Database, "alfred_roles_test") {
		t.Fatal("requires disposable alfred_roles_test database")
	}
	root, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	schema := "roles_" + strings.ReplaceAll(uuid.NewString(), "-", "")
	if _, err = root.Exec(ctx, "CREATE SCHEMA "+schema); err != nil {
		t.Fatal(err)
	}
	defer root.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE")
	cfg.ConnConfig.RuntimeParams["search_path"] = schema
	db, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	migration, err := os.ReadFile("../../migrations/001_init.up.sql")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(ctx, string(migration)); err != nil {
		t.Fatal(err)
	}
	auth := service.NewAuthService(db, testSecret, time.Minute, time.Hour, "test-admin-password")
	if err = auth.SeedAdmin(ctx); err != nil {
		t.Fatal(err)
	}
	member, err := auth.Register(ctx, service.RegisterRequest{Username: "regular_user", Password: "test-user-password"})
	if err != nil {
		t.Fatal(err)
	}
	unused, err := auth.Register(ctx, service.RegisterRequest{Username: "<img src=x>", Password: "test-user-password"})
	if err != nil {
		t.Fatal(err)
	}
	_, err = db.Exec(ctx, `UPDATE admin_users SET is_active=false WHERE id=$1`, unused.ID)
	if err != nil {
		t.Fatal(err)
	}
	_, err = db.Exec(ctx, `INSERT INTO admin_token_usage(user_id,provider,model_name,input_tokens,output_tokens,total_tokens,created_at)
		VALUES ($1,'test','model',100,20,120,NOW()),($1,'test','model',30,10,40,NOW()),
		($1,'test','model',1000,200,1200,NOW()-INTERVAL '31 days')`, member.ID)
	if err != nil {
		t.Fatal(err)
	}
	r := chi.NewRouter()
	mw := NewMiddleware(testSecret)
	authHandler := NewAuthHandler(auth)
	r.Post("/auth/login", authHandler.Login)
	r.Post("/auth/register", authHandler.Register)
	r.Route("/admin", func(r chi.Router) {
		r.Use(mw.Auth)
		r.Use(mw.AdminOnly)
		NewUserHandler(service.NewUserDirectory(db)).RegisterRoutes(r)
	})
	request := func(method, path, body, token string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(method, path, strings.NewReader(body))
		if token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		return w
	}
	login := func(username, password string) string {
		body, _ := json.Marshal(map[string]string{"username": username, "password": password})
		w := request("POST", "/auth/login", string(body), "")
		if w.Code != 200 {
			t.Fatalf("login %s: %d", username, w.Code)
		}
		var pair service.TokenPair
		if err := json.Unmarshal(w.Body.Bytes(), &pair); err != nil {
			t.Fatal(err)
		}
		return pair.AccessToken
	}
	adminToken, userToken := login("admin", "test-admin-password"), login("regular_user", "test-user-password")
	for _, path := range []string{"/admin/users", "/admin/overview"} {
		if request("GET", path, "", "").Code != 401 || request("GET", path, "", userToken).Code != 403 {
			t.Fatal("authorization boundary failed")
		}
	}
	w := request("GET", "/admin/users", "", adminToken)
	if w.Code != 200 {
		t.Fatalf("list: %d %s", w.Code, w.Body.String())
	}
	var page service.UserPage
	if err := json.Unmarshal(w.Body.Bytes(), &page); err != nil {
		t.Fatal(err)
	}
	if page.Total != 3 || len(page.Users) != 3 {
		t.Fatalf("accounts missing: %+v", page)
	}
	for _, u := range page.Users {
		if u.ID == member.ID.String() && (u.Calls != 2 || u.TotalTokens != 160 || u.InputTokens != 130 || u.OutputTokens != 30 || u.LastUsedAt == nil) {
			t.Fatalf("usage incorrect: %+v", u)
		}
		if u.ID == unused.ID.String() && (u.Calls != 0 || u.IsActive || u.LastUsedAt != nil) {
			t.Fatalf("zero-use account incorrect: %+v", u)
		}
	}
	if strings.Contains(w.Body.String(), "password") || strings.Contains(w.Body.String(), "token_hash") {
		t.Fatal("credential exposed")
	}
	w = request("GET", "/admin/overview", "", adminToken)
	var summary service.UsageOverview
	if err := json.Unmarshal(w.Body.Bytes(), &summary); err != nil {
		t.Fatal(err)
	}
	if summary.TotalUsers != 3 || summary.AdminUsers != 1 || summary.ActiveUsers != 2 || summary.Calls != 2 || summary.TotalTokens != 160 {
		t.Fatalf("summary incorrect: %+v", summary)
	}
	for _, test := range []struct {
		path  string
		total int64
		size  int
	}{
		{"/admin/users?role=admin", 1, 1}, {"/admin/users?q=regular", 1, 1},
		{"/admin/users?q=" + member.ID.String(), 1, 1}, {"/admin/users?q=%25", 0, 0},
		{"/admin/users?page_size=1&page=2", 3, 1}, {"/admin/users?page=99", 3, 0},
	} {
		w = request("GET", test.path, "", adminToken)
		var got service.UserPage
		if err := json.Unmarshal(w.Body.Bytes(), &got); err != nil {
			t.Fatal(err)
		}
		if w.Code != 200 || got.Total != test.total || len(got.Users) != test.size {
			t.Fatalf("filter %s: %s", test.path, w.Body.String())
		}
	}
	for _, query := range []string{"page=-1", "page=no", "page_size=999", "role=owner", "q=" + strings.Repeat("x", 65)} {
		if request("GET", "/admin/users?"+query, "", adminToken).Code != 400 {
			t.Fatal("invalid filter accepted", query)
		}
	}
	w = request("POST", "/auth/register", `{"username":"attacker","password":"test-password","role":"admin"}`, "")
	if w.Code != 201 {
		t.Fatal("registration failed")
	}
	token := login("attacker", "test-password")
	if request("GET", "/admin/users", "", token).Code != 403 {
		t.Fatal("registration elevated role")
	}
	if request("POST", "/auth/login", `{"username":"<img src=x>","password":"test-user-password"}`, "").Code != 401 {
		t.Fatal("disabled account logged in")
	}
}
