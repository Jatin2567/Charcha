// Install immediately after admin-challenge. The claim is issued after a successful challenge.
exports.onExecutePostLogin = async (event, api) => {
  if (event.client.client_id !== event.secrets.CHARCHA_CLIENT_ID ||
      event.user.user_id !== event.secrets.CHARCHA_ADMIN_SUBJECT) return;
  const methods = event.authentication?.methods || [];
  const fresh = name => methods.some(method => {
    const age = Date.now() - Date.parse(method.timestamp);
    return method.name === name && age >= 0 && age <= 300_000;
  });
  if (!fresh("pwd") || !fresh("mfa")) return api.access.deny("A fresh administrator second factor is required.");
  api.idToken.setCustomClaim("https://charcha.app/mfa", true);
};
