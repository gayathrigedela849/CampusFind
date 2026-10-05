# CampusFind — Smart Campus Lost & Found Management System

## Stack
- Python
- Flask
- SQLite
- HTML
- CSS
- JavaScript

## Main features
- Student registration and secure password hashing
- Login/logout with sessions
- Student dashboard
- Report lost item
- Report found item
- Public preview image
- Private verification image/details
- Found item search and category filtering
- Ownership claim workflow
- Claim status tracking
- Notifications
- Admin/HOD dashboard
- Admin item management
- Admin claim verification
- Mark item ready for collection / returned
- Responsive light/dark UI

## Run
```bash
python app.py
```

Open:
http://127.0.0.1:5000

## Default admin
Email:
admin@campusfind.local

Password:
Admin@123

Change the admin password/account before real deployment.

## Important
The private verification image is only served through an admin-protected route.
Do not place private verification images in a public static folder in a production deployment.
For a real deployment, also move the secret key into an environment variable.
## Deployment

### Local Setup

1. Create and activate a virtual environment.
2. Install the required packages:

```bash
pip install -r requirements.txt
