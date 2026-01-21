"""Admin endpoints (/api/admin/*)."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends

from auth import (
    AuthenticatedUser,
    get_current_admin,
    hash_password,
)
from db_instance import db
from models import (
    AdminUserCreate,
    GroupCreate,
    GroupUpdate,
    GroupMemberAdd,
    RegistrationToggle,
    CheckerSettings,
    CheckerSettingsResponse,
    ConfigUpdate,
    DiscordWebhookConfig,
    TestWebhookResponse,
)
from discord_client import send_test_notification

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Default checker settings (used if not configured in database)
DEFAULT_CHECK_INTERVAL = 120
DEFAULT_NOTIFICATION_THRESHOLD = 60


# ============ User Management ============

@router.get("/users")
async def admin_get_users(admin: AuthenticatedUser = Depends(get_current_admin)):
    """Get all users. Requires admin access."""
    users = await db.get_all_users()
    return users


@router.get("/users/{user_id}")
async def admin_get_user(
    user_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Get detailed user info. Requires admin access."""
    user = await db.admin_get_user_details(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/users/{user_id}")
async def admin_update_user(
    user_id: int,
    is_active: Optional[bool] = None,
    is_admin: Optional[bool] = None,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Update user status. Requires admin access."""
    # Prevent admin from demoting themselves
    if user_id == admin.user_id and is_admin is False:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin status")
    
    success = await db.admin_update_user(user_id, is_active=is_active, is_admin=is_admin)
    if not success:
        raise HTTPException(status_code=404, detail="User not found or no changes made")
    return {"status": "ok", "message": "User updated"}


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Delete a user. Requires admin access."""
    # Prevent admin from deleting themselves
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    success = await db.admin_delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "ok", "message": "User deleted"}


@router.post("/users")
async def admin_create_user(
    user_data: AdminUserCreate,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Create a new user. Requires admin access."""
    # Hash the password
    hashed_password = hash_password(user_data.password)
    
    try:
        user_id = await db.admin_create_user(
            email=user_data.email,
            username=user_data.username,
            password_hash=hashed_password,
            is_active=user_data.is_active,
            is_admin=user_data.is_admin
        )
        return {"status": "ok", "user_id": user_id, "message": "User created successfully"}
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=400, detail="Email or username already exists")
        raise HTTPException(status_code=400, detail=str(e))


# ============ Settings ============

@router.get("/settings/registration")
async def admin_get_registration_setting(
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Get registration enabled status. Requires admin access."""
    allow_registration = await db.get_config("allow_registration")
    return {"allow_registration": allow_registration == "true"}


@router.put("/settings/registration")
async def admin_toggle_registration(
    settings: RegistrationToggle,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Enable or disable public registration. Requires admin access."""
    await db.set_config("allow_registration", "true" if settings.allow_registration else "false")
    return {"status": "ok", "allow_registration": settings.allow_registration}


@router.get("/settings/checker", response_model=CheckerSettingsResponse)
async def admin_get_checker_settings(
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Get checker agent settings. Requires admin access."""
    check_interval = await db.get_config("check_interval_seconds")
    notification_threshold = await db.get_config("notification_threshold_minutes")
    
    return CheckerSettingsResponse(
        check_interval_seconds=int(check_interval) if check_interval else DEFAULT_CHECK_INTERVAL,
        notification_threshold_minutes=int(notification_threshold) if notification_threshold else DEFAULT_NOTIFICATION_THRESHOLD
    )


@router.put("/settings/checker", response_model=CheckerSettingsResponse)
async def admin_update_checker_settings(
    settings: CheckerSettings,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Update checker agent settings. Requires admin access.
    
    Checker agents will pick up these changes on their next cycle.
    """
    await db.set_config("check_interval_seconds", str(settings.check_interval_seconds))
    await db.set_config("notification_threshold_minutes", str(settings.notification_threshold_minutes))
    
    return CheckerSettingsResponse(
        check_interval_seconds=settings.check_interval_seconds,
        notification_threshold_minutes=settings.notification_threshold_minutes
    )


# ============ Group Management ============

@router.get("/groups")
async def admin_get_groups(
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Get all groups. Requires admin access."""
    groups = await db.get_all_groups()
    return groups


@router.post("/groups")
async def admin_create_group(
    group_data: GroupCreate,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Create a new group. Requires admin access."""
    try:
        group_id = await db.create_group(
            name=group_data.name,
            description=group_data.description,
            created_by=admin.user_id
        )
        return {"status": "ok", "group_id": group_id, "message": "Group created successfully"}
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=400, detail="Group name already exists")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/groups/{group_id}")
async def admin_get_group(
    group_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Get group details. Requires admin access."""
    group = await db.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.put("/groups/{group_id}")
async def admin_update_group(
    group_id: int,
    group_data: GroupUpdate,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Update a group. Requires admin access."""
    success = await db.update_group(
        group_id=group_id,
        name=group_data.name,
        description=group_data.description
    )
    if not success:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"status": "ok", "message": "Group updated"}


@router.delete("/groups/{group_id}")
async def admin_delete_group(
    group_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Delete a group. Requires admin access."""
    success = await db.delete_group(group_id)
    if not success:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"status": "ok", "message": "Group deleted"}


@router.get("/groups/{group_id}/members")
async def admin_get_group_members(
    group_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Get all members of a group. Requires admin access."""
    # Verify group exists
    group = await db.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    members = await db.get_group_members(group_id)
    return members


@router.post("/groups/{group_id}/members")
async def admin_add_group_member(
    group_id: int,
    member_data: GroupMemberAdd,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Add a user to a group. Requires admin access."""
    # Verify group exists
    group = await db.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    try:
        await db.add_group_member(
            group_id=group_id,
            user_id=member_data.user_id,
            role=member_data.role
        )
        return {"status": "ok", "message": "Member added to group"}
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=400, detail="User is already a member of this group")
        if "foreign key" in str(e).lower():
            raise HTTPException(status_code=400, detail="User not found")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/groups/{group_id}/members/{user_id}")
async def admin_remove_group_member(
    group_id: int,
    user_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Remove a user from a group. Requires admin access."""
    success = await db.remove_group_member(group_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Member not found in group")
    return {"status": "ok", "message": "Member removed from group"}
