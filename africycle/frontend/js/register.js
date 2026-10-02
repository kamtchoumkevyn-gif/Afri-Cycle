// Register page

(function () {
  const form = document.getElementById("registerForm");
  const submitBtn = document.getElementById("submitBtn");
  const btnText = document.getElementById("btnText");
  const btnSpinner = document.getElementById("btnSpinner");
  const formMsg = document.getElementById("formMsg");

  function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    btnText.hidden = isLoading;
    btnSpinner.hidden = !isLoading;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    formMsg.hidden = true;

    const name = document.getElementById("name").value.trim();
    const phoneNumber = document.getElementById("phoneNumber").value.trim();
    const role = document.getElementById("role").value;
    const password = document.getElementById("password").value;
    const confirmPassword = document.getElementById("confirmPassword").value;

    if (!name || !phoneNumber || !role || !password) {
      showMessage(formMsg, "Fill in every field to create your account.", "error");
      return;
    }
    if (password.length < 6) {
      showMessage(formMsg, "Use a password with at least 6 characters.", "error");
      return;
    }
    if (password !== confirmPassword) {
      showMessage(formMsg, "The two passwords don't match.", "error");
      return;
    }

    setLoading(true);
    try {
      const response = await apiFetch("/register", {
        method: "POST",
        body: JSON.stringify({ name, phoneNumber, password, role })
      });
      const data = await readJson(response);

      if (!response.ok) {
        showMessage(formMsg, data.message || "Account not created. Check your details and try again.", "error");
        setLoading(false);
        return;
      }

      showMessage(formMsg, "Account created. Taking you to log in...", "success");
      setTimeout(() => window.location.replace("login.html"), 1200);
    } catch (err) {
      showMessage(formMsg, "Can't reach the server. Make sure the backend is running, then try again.", "error");
      setLoading(false);
    }
  });
})();
