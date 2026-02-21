const admin = require("firebase-admin");
const serviceAccount = require("./serviceAccount.json");

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
});

(async () => {
  const uid = "V7nobiuienQ4dUH7usDkSbn9rRA2";

  await admin.auth().setCustomUserClaims(uid, { admin: true });

  console.log("Admin claim set ✅");
})();