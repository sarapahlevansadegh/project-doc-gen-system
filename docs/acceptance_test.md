# Final Acceptance Test Checklist

Use this checklist to verify the system is ready for customer delivery.

## Prerequisites

- Docker and Docker Compose installed
- Ports 80, 8000, and 5433 are available
- At least 4GB RAM available

## Setup

```bash
# 1. Start services
docker-compose up -d

# 2. Run migrations
docker-compose exec backend alembic upgrade head

# 3. Create admin user
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "AdminPass123!",
    "full_name": "System Admin",
    "role": "admin"
  }'
```

## Test Scenarios

### 1. Authentication

- [ ] **Login as Admin**
  - Navigate to http://localhost
  - Enter admin credentials
  - Verify redirect to dashboard
  - Verify email and "admin" badge visible in navbar

- [ ] **Create Engineer User**
  - Note: User management UI not implemented yet
  - Use API directly:
    ```bash
    curl -X POST http://localhost:8000/auth/register \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <admin_token>" \
      -d '{
        "email": "engineer@example.com",
        "password": "EngineerPass123!",
        "full_name": "Engineer User",
        "role": "engineer"
      }'
    ```
  - Verify 201 response

- [ ] **Create Viewer User**
  ```bash
  curl -X POST http://localhost:8000/auth/register \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <admin_token>" \
    -d '{
      "email": "viewer@example.com",
      "password": "ViewerPass123!",
      "full_name": "Viewer User",
      "role": "viewer"
    }'
  ```
  - Verify 201 response

- [ ] **Logout**
  - Click Logout button
  - Verify redirect to /login
  - Verify tokens cleared

### 2. Device Management

- [ ] **Login as Engineer**
  - Verify access to Devices page

- [ ] **Create Device**
  - Navigate to Devices
  - Click "Create Device"
  - Fill in device details:
    - Name: "Test Device VL8"
    - Model: "VL8"
    - Document Code: "15799"
    - Safety Class: B
    - Driver Version: "01"
    - GUI Version: "7.0.0.1"
  - Add a spec: Category="laser", Key="wavelength", Value="808nm"
  - Add an alarm: Condition="overheat", Sound=true
  - Add a command: Name="CMD1", Direction="main_to_panel"
  - Click Create
  - Verify device appears in list

- [ ] **Viewer Cannot Create Device**
  - Login as Viewer
  - Navigate to Devices
  - Verify no "Create Device" button (or verify API returns 403)

### 3. Reference Documents

- [ ] **Upload Reference DOCX**
  - Login as Engineer
  - Navigate to References
  - Click "Upload Reference"
  - Select a .docx file
  - Verify upload success message
  - Verify reference appears in list with sections

- [ ] **Activate Reference**
  - Click "Activate" on uploaded reference
  - Verify "Active" badge appears
  - Verify only one reference is active at a time

- [ ] **Viewer Can View References**
  - Login as Viewer
  - Navigate to References
  - Verify reference list is visible
  - Verify no upload/activate/delete buttons

### 4. Document Generation

- [ ] **Generate Document**
  - Login as Engineer
  - Navigate to Generate
  - Select device
  - Select reference document
  - Click "Generate Document"
  - Verify job_id is shown
  - Verify WebSocket progress updates
  - Verify status changes to "completed"
  - Verify "Download Document" button appears

- [ ] **Viewer Cannot Generate**
  - Login as Viewer
  - Navigate to Generate
  - Verify generate button is disabled or API returns 403

### 5. History

- [ ] **View Generation History**
  - Login as any role
  - Navigate to History
  - Select a device
  - Verify generated documents appear
  - Verify version numbers are correct
  - Verify download button works for completed documents

### 6. Downloads

- [ ] **Download Generated Document**
  - From History page, click Download
  - Verify .docx file downloads
  - Verify file opens correctly

### 7. Error Handling

- [ ] **Invalid Login**
  - Enter wrong password
  - Verify error message

- [ ] **Missing Device**
  - Try to generate for non-existent device
  - Verify 404 error

- [ ] **No Active Reference**
  - Deactivate all references
  - Try to generate without selecting reference
  - Verify appropriate error

## Known Limitations

1. **User Management UI**: Users must be created via API curl commands
2. **Refresh Tokens**: Not implemented - users must re-login after token expiry (15 min)
3. **Password Reset**: Not implemented
4. **WebSocket**: Requires token in query parameter (`?token=...`)
5. **PostgreSQL Required**: Tests and full functionality require PostgreSQL running

## Rollback

If issues occur:

```bash
# Stop services
docker-compose down

# Remove volumes (WARNING: destroys data)
docker-compose down -v

# Restart
docker-compose up -d
```
