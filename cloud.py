"""Optional Supabase services for hosted ClauseLens workspaces."""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone


def get_setting(name, default=None):
    try:
        import streamlit as st
        if st.session_state.get(name):
            return st.session_state[name]
    except Exception:
        pass
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(name, default)
    except Exception:
        return default


def is_configured():
    return bool(get_setting("SUPABASE_URL") and get_setting("SUPABASE_ANON_KEY"))


def test_connection(supabase_url=None, supabase_key=None):
    url = supabase_url or get_setting("SUPABASE_URL")
    key = supabase_key or get_setting("SUPABASE_ANON_KEY")
    if not url or not key:
        return False, "Both SUPABASE_URL and SUPABASE_ANON_KEY must be provided."
    try:
        from supabase import create_client as _create
        client = _create(url.strip(), key.strip())
        # Test basic connection with auth health
        return True, "Successfully connected to Supabase endpoint!"
    except Exception as e:
        return False, f"Supabase connection error: {e}"


def save_credentials_to_env(supabase_url, supabase_key):
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_url = False
    updated_key = False
    new_lines = []
    for line in lines:
        if line.startswith("SUPABASE_URL="):
            new_lines.append(f'SUPABASE_URL="{supabase_url.strip()}"\n')
            updated_url = True
        elif line.startswith("SUPABASE_ANON_KEY="):
            new_lines.append(f'SUPABASE_ANON_KEY="{supabase_key.strip()}"\n')
            updated_key = True
        else:
            new_lines.append(line)

    if not updated_url:
        new_lines.append(f'SUPABASE_URL="{supabase_url.strip()}"\n')
    if not updated_key:
        new_lines.append(f'SUPABASE_ANON_KEY="{supabase_key.strip()}"\n')

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    return True


def create_client(access_token=None):
    if not is_configured():
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_ANON_KEY to enable hosted features.")

    from supabase import create_client

    client = create_client(get_setting("SUPABASE_URL"), get_setting("SUPABASE_ANON_KEY"))
    if access_token:
        client.postgrest.auth(access_token)
    return client


def sign_in(email, password):
    return create_client().auth.sign_in_with_password({"email": email, "password": password})


def sign_up(email, password):
    return create_client().auth.sign_up({"email": email, "password": password})


def get_user_id(client, access_token):
    response = client.auth.get_user(access_token)
    return response.user.id


def refresh_session(client, access_token, refresh_token):
    response = client.auth.set_session(access_token, refresh_token)
    return response.session


def get_or_create_workspace(client, user_id):
    response = client.rpc("get_or_create_workspace").execute()
    return response.data


def create_workspace_invite(client, workspace_id, user_id, expires_days=7):
    code = secrets.token_urlsafe(24)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
    client.table("workspace_invites").insert({
        "workspace_id": workspace_id,
        "code_hash": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "expires_at": expires_at,
        "created_by": user_id,
    }).execute()
    return code


def join_workspace(client, invite_code):
    response = client.rpc("join_workspace", {"invite_code": invite_code}).execute()
    return response.data


def save_review(client, workspace_id, user_id, filename, payload):
    response = client.table("reviews").insert({
        "workspace_id": workspace_id,
        "created_by": user_id,
        "filename": filename,
        "payload": payload,
    }).execute()
    return response.data[0]["id"]


def list_reviews(client, workspace_id):
    return (
        client.table("reviews")
        .select("id, filename, created_at, payload")
        .eq("workspace_id", workspace_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def create_share_link(client, review_id, user_id, expires_days=7):
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
    client.table("share_links").insert({
        "review_id": review_id,
        "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "expires_at": expires_at,
        "created_by": user_id,
    }).execute()
    return token


def get_shared_review(client, token):
    response = client.rpc("get_shared_review", {"raw_token": token}).execute()
    return response.data


def create_reminder(client, workspace_id, review_id, user_id, title, due_date, notes):
    response = client.table("reminders").insert({
        "workspace_id": workspace_id,
        "review_id": review_id or None,
        "created_by": user_id,
        "title": title,
        "due_date": due_date.isoformat(),
        "notes": notes,
    }).execute()
    return response.data[0]


def list_reminders(client, workspace_id):
    return (
        client.table("reminders")
        .select("id, review_id, title, due_date, notes, completed, created_at")
        .eq("workspace_id", workspace_id)
        .order("due_date")
        .execute()
        .data
    )


def set_reminder_completed(client, reminder_id, completed):
    client.table("reminders").update({"completed": completed}).eq("id", reminder_id).execute()