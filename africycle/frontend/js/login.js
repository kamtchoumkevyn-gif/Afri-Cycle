// Login page

(function () {
  const form = document.getElementById("loginForm");
  const submitBtn = document.getElementById("submitBtn");
  const btnText = document.getElementById("btnText");
  const btnSpinner = document.getElementById("btnSpinner");
  const formMsg = document.getElementById("formMsg");

  const existingUser = currentUser();
  if (existingUser) {
    window.location.replace(dashboardFor(existingUser.role));
    return;
  }

  function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    btnText.hidden = isLoading;
    btnSpinner.hidden = !isLoading;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    formMsg.hidden = true;

    const phoneNumber = document.getElementById("phoneNumber").value.trim();
    const role = document.getElementById("role").value;
    const password = document.getElementById("password").value;
    const remember = document.getElementById("rememberMe").checked;

    if (!phoneNumber || !role || !password) {
      showMessage(formMsg, "Enter your phone number, choose a role, and enter your password.", "error");
      return;
    }

    setLoading(true);
    try {
      const response = await apiFetch("/login", {
        method: "POST",
        body: JSON.stringify({ phoneNumber, password, role })
      });
      const data = await readJson(response);

      if (!response.ok) {
        const text = response.status === 429
          ? "Too many attempts. Wait a minute, then try again."
          : (data.message || "Login failed. Check your details and try again.");
        showMessage(formMsg, text, "error");
        setLoading(false);
        return;
      }

      saveToken(data.token, remember);
      // A "both" account goes to whichever side it chose at login
      window.location.replace(dashboardFor(data.role === "both" ? role : data.role));
    } catch (err) {
      showMessage(formMsg, "Can't reach the server. Make sure the backend is running, then try again.", "error");
      setLoading(false);
    }
  });
})();
