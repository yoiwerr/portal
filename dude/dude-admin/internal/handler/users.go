package handler

import (
	"net/http"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/go-chi/chi/v5"
	"github.com/yoiwerr/portal/dude/dude-admin/internal/service"
	"github.com/yoiwerr/portal/dude/dude-admin/pkg/response"
)

type UserHandler struct{ directory *service.UserDirectory }

func NewUserHandler(directory *service.UserDirectory) *UserHandler {
	return &UserHandler{directory: directory}
}

// RegisterRoutes must be mounted under the authenticated admin route group.
func (h *UserHandler) RegisterRoutes(r chi.Router) {
	r.Get("/users", h.List)
	r.Get("/overview", h.Overview)
}

func (h *UserHandler) Overview(w http.ResponseWriter, r *http.Request) {
	result, err := h.directory.Overview(r.Context())
	if err != nil {
		response.WriteError(w, r, http.StatusInternalServerError, "INTERNAL_ERROR", "暂时无法读取用量概览，请重试")
		return
	}
	response.WriteJSON(w, http.StatusOK, result)
}

func (h *UserHandler) List(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	search, role := strings.TrimSpace(q.Get("q")), q.Get("role")
	page, size := 1, 20
	var err error
	if q.Has("page") {
		page, err = strconv.Atoi(q.Get("page"))
	}
	if err != nil || page < 1 || page > 1000000 {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "无效的页码")
		return
	}
	if q.Has("page_size") {
		size, err = strconv.Atoi(q.Get("page_size"))
	}
	if err != nil || size < 1 || size > 100 || utf8.RuneCountInString(search) > 64 ||
		(role != "" && role != "admin" && role != "user") {
		response.WriteError(w, r, http.StatusBadRequest, "VALIDATION_ERROR", "无效的筛选条件")
		return
	}
	result, err := h.directory.List(r.Context(), search, role, page, size)
	if err != nil {
		response.WriteError(w, r, http.StatusInternalServerError, "INTERNAL_ERROR", "暂时无法读取用户信息，请重试")
		return
	}
	response.WriteJSON(w, http.StatusOK, result)
}
