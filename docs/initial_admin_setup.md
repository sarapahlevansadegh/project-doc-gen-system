# Initial Admin Setup

Since this system starts with zero users, you must create an admin user before logging in.

## Option 1: Using the API (Recommended)

Once the backend is running:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "YourSecurePassword123!",
    "full_name": "Admin User",
    "role": "admin"
  }'
```

## Option 2: Using the Frontend

1. Open the application in your browser
2. Click "Sign in" or navigate to `/login`
3. Use the "Register" form (if available) or contact your system administrator

## Default Roles

| Role | Access |
|------|--------|
| `admin` | Full access to all features |
| `engineer` | Create/edit devices, upload references, generate documents |
| `viewer` | Read-only access to devices, references, history, and downloads |

## Notes

- Passwords must be at least 8 characters
- The first user should be created with `role: "admin"`
- Maximum recommended users: 3 (as per system design)
- For production, change the `secret_key` in `.env` to a secure random value
