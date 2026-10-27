# [BUG] Cannot delete account on settings page

### Environment
- **Version:** v1.1.0
- **Browser:** Chrome 124 / macOS

### Steps to Reproduce
1. Navigate to `/settings`
2. Click the "Delete Account" button

### Expected Behavior
The account should be deleted successfully and a green success notification "Account deleted successfully" should appear.

### Actual Behavior
The button triggers a red error banner "Something went wrong". The account is not deleted, and the console reports a 500 server error on `/api/delete-account`.
