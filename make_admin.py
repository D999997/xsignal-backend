import os
import sys
import json
import firebase_admin
from firebase_admin import credentials, auth

def init_firebase():
    if firebase_admin._apps:
        return

    firebase_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")

    if firebase_json:
        cred = credentials.Certificate(json.loads(firebase_json))
        firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized (env)")
        return

    if os.path.exists("firebase_admin.json"):
        cred = credentials.Certificate("firebase_admin.json")
        firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized (file)")
        return

    raise Exception("❌ Firebase credentials not found.")

def make_admin(uid: str):
    auth.set_custom_user_claims(uid, {"admin": True})
    print(f"✅ SUCCESS: {uid} is now ADMIN")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python make_admin.py <USER_UID>")
        sys.exit(1)

    uid = sys.argv[1]
    init_firebase()
    make_admin(uid)