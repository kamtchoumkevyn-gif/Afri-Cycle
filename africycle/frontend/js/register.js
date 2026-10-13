// Register page

(function () {
  const form = document.getElementById("registerForm");
  const submitBtn = document.getElementById("submitBtn");
  const btnText = document.getElementById("btnText");
  const btnSpinner = document.getElementById("btnSpinner");
  const formMsg = document.getElementById("formMsg");
  const isMinorBox = document.getElementById("isMinor");
  const guardianFields = document.getElementById("guardianFields");
  const roleSelect = document.getElementById("role");
  const roleHint = document.getElementById("roleHint");
  const phoneCountry = document.getElementById("phoneCountry");
  const guardianCountry = document.getElementById("guardianCountry");

  // Any of the 11 Central African countries; the guardian's starts as the same one
  AfriPhone.setUp(phoneCountry, document.getElementById("phoneNumber"), document.getElementById("phoneCode"));
  AfriPhone.setUp(guardianCountry, document.getElementById("guardianPhone"), document.getElementById("guardianCode"),
    { follow: phoneCountry });

  function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    btnText.hidden = isLoading;
    btnSpinner.hidden = !isLoading;
  }

  // Under-18s register as sellers, supervised by a guardian
  isMinorBox.addEventListener("change", () => {
    const minor = isMinorBox.checked;
    guardianFields.hidden = !minor;
    roleHint.hidden = !minor;
    roleSelect.disabled = minor;
    if (minor) roleSelect.value = "seller";
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    formMsg.hidden = true;

    const name = document.getElementById("name").value.trim();
    const phoneNumber = document.getElementById("phoneNumber").value.trim();
    const role = roleSelect.value;
    const password = document.getElementById("password").value;
    const confirmPassword = document.getElementById("confirmPassword").value;
    const isMinor = isMinorBox.checked;

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

    const body = { name, phoneNumber, country: phoneCountry.value, password, role };
    if (isMinor) {
      body.isMinor = true;
      body.guardianName = document.getElementById("guardianName").value.trim();
      body.guardianPhone = document.getElementById("guardianPhone").value.trim();
      body.guardianCountry = guardianCountry.value;
      body.guardianRelation = document.getElementById("guardianRelation").value;
      if (!body.guardianName || !body.guardianPhone || !body.guardianRelation) {
        showMessage(formMsg, "Fill in your guardian's name, phone number and how they are related to you.", "error");
        return;
      }
    }

    setLoading(true);
    try {
      const response = await apiFetch("/register", {
        method: "POST",
        body: JSON.stringify(body)
      });
      const data = await readJson(response);

      if (!response.ok) {
        showMessage(formMsg, data.message || "Account not created. Check your details and try again.", "error");
        setLoading(false);
        return;
      }

      showMessage(formMsg, isMinor
        ? "Account created. Ask your guardian to create their Africycle account with their phone number and approve you. Taking you to log in..."
        : "Account created. Taking you to log in...", "success");
      setTimeout(() => window.location.replace("login.html"), isMinor ? 4000 : 1200);
    } catch (err) {
      showMessage(formMsg, "Can't reach the server. Make sure the backend is running, then try again.", "error");
      setLoading(false);
    }
  });
})();
