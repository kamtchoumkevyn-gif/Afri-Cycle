// Login page

AfriI18n.whenReady(function () {
  const form = document.getElementById("loginForm");
  const submitBtn = document.getElementById("submitBtn");
  const btnText = document.getElementById("btnText");
  const btnSpinner = document.getElementById("btnSpinner");
  const formMsg = document.getElementById("formMsg");
  const phoneCountry = document.getElementById("phoneCountry");
  const codeField = document.getElementById("codeField");
  const codeInput = document.getElementById("twoStepCode");

  const existingUser = currentUser();
  if (existingUser) {
    window.location.replace(dashboardFor(existingUser.role));
    return;
  }

  AfriPhone.setUp(phoneCountry, document.getElementById("phoneNumber"), document.getElementById("phoneCode"));

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
      showMessage(formMsg, t("Enter your phone number, choose a role, and enter your password."), "error");
      return;
    }

    setLoading(true);
    try {
      const response = await apiFetch("/login", {
        method: "POST",
        body: JSON.stringify({ phoneNumber, country: phoneCountry.value, password, role,
          code: codeField.hidden ? undefined : codeInput.value.trim() })
      });
      const data = await readJson(response);

      // Admins with two-step login on: show the code box, then log in again with the code
      if (response.status === 401 && data.code === "two_step_required") {
        codeField.hidden = false;
        codeInput.value = "";
        showMessage(formMsg, data.message, "error");
        setLoading(false);
        codeInput.focus();
        return;
      }

      if (!response.ok) {
        const text = response.status === 429
          ? t("Too many attempts. Wait a minute, then try again.")
          : (data.message || t("Login failed. Check your details and try again."));
        showMessage(formMsg, text, "error");
        setLoading(false);
        return;
      }

      saveToken(data.token, remember);
      // A "both" account goes to whichever side it chose at login
      window.location.replace(dashboardFor(data.role === "both" ? role : data.role));
    } catch (err) {
      showMessage(formMsg, t("Can't reach the server. Check your connection, then try again."), "error");
      setLoading(false);
    }
  });
});
