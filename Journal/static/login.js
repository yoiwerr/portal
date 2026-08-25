const form = document.querySelector("#loginForm");
const errorMessage = document.querySelector("#loginError");
const submitButton = form.querySelector('button[type="submit"]');

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorMessage.textContent = "";
  submitButton.disabled = true;
  submitButton.textContent = "登录中...";

  const payload = {
    username: form.username.value,
    password: form.password.value,
  };

  try {
    const response = await fetch("/journal/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "登录失败");
    }

    window.location.replace("/journal/");
  } catch (error) {
    errorMessage.textContent = error.message;
    submitButton.disabled = false;
    submitButton.textContent = "登录";
  }
});
