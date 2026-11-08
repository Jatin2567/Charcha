// Install as the first Auth0 Post Login Action. Configure the two Action secrets.
exports.onExecutePostLogin = async (event, api) => {
  if (event.client.client_id !== event.secrets.CHARCHA_CLIENT_ID ||
      event.user.user_id !== event.secrets.CHARCHA_ADMIN_SUBJECT) return;
  api.authentication.challengeWith({ type: "otp" });
};
