from dataclasses import dataclass
from enum import StrEnum

from fastapi import HTTPException, status

from idml_foundation.models import User


class Role(StrEnum):
    ORG_ADMIN = "org_admin"
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    RELEASE_MANAGER = "release_manager"


class Permission(StrEnum):
    ORGANIZATION_MANAGE = "organization:manage"
    MEMBERSHIP_MANAGE = "membership:manage"
    RESOURCE_READ = "resource:read"
    RESOURCE_WRITE = "resource:write"
    ARTIFACT_UPLOAD = "artifact:upload"
    JOB_CREATE = "job:create"
    JOB_READ = "job:read"
    REVIEW_WRITE = "review:write"
    RELEASE_REQUEST = "release:request"
    RELEASE_APPROVE = "release:approve"
    AUDIT_READ = "audit:read"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ORG_ADMIN: frozenset(Permission),
    Role.OPERATOR: frozenset(
        {
            Permission.RESOURCE_READ,
            Permission.RESOURCE_WRITE,
            Permission.ARTIFACT_UPLOAD,
            Permission.JOB_CREATE,
            Permission.JOB_READ,
            Permission.RELEASE_REQUEST,
        }
    ),
    Role.REVIEWER: frozenset(
        {
            Permission.RESOURCE_READ,
            Permission.JOB_READ,
            Permission.REVIEW_WRITE,
            Permission.RELEASE_REQUEST,
        }
    ),
    Role.RELEASE_MANAGER: frozenset(
        {
            Permission.RESOURCE_READ,
            Permission.JOB_READ,
            Permission.RELEASE_REQUEST,
            Permission.RELEASE_APPROVE,
            Permission.AUDIT_READ,
        }
    ),
}


@dataclass(frozen=True)
class TenantContext:
    user: User
    organization_id: str
    role: Role

    def allows(self, permission: Permission) -> bool:
        if self.user.is_platform_admin:
            return True
        return permission in ROLE_PERMISSIONS.get(self.role, frozenset())

    def require(self, permission: Permission) -> None:
        if not self.allows(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")


def assert_same_tenant(context: TenantContext, resource_organization_id: str) -> None:
    if context.organization_id != resource_organization_id:
        # Return not found so callers cannot enumerate cross-tenant identifiers.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource not found")
