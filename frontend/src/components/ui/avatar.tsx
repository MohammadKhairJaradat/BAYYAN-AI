import { useState } from "react";
import type { User } from "../../types/api";
import { Mark } from "../brand";

type UserAvatarProps = {
  user: Pick<User, "name" | "username" | "avatar_url"> | null | undefined;
  className?: string;
};

type TaxAiAvatarProps = {
  className?: string;
};

function getInitial(user: UserAvatarProps["user"]): string {
  const source = user?.name || user?.username || "U";
  return source.trim().charAt(0).toUpperCase() || "U";
}

export function UserAvatar({ user, className = "" }: UserAvatarProps) {
  const avatarUrl = user?.avatar_url?.trim() || "";
  const [failedUrl, setFailedUrl] = useState<string | null>(null);

  return (
    <div
      className={`rounded-full flex items-center justify-center font-bold overflow-hidden ${className}`}
      style={{ background: "var(--green-tint)", border: "1px solid var(--green-tint2)", color: "var(--green)" }}
    >
      {avatarUrl && avatarUrl !== failedUrl ? (
        <img
          src={avatarUrl}
          alt="User avatar"
          className="w-full h-full object-cover"
          onError={() => setFailedUrl(avatarUrl)}
        />
      ) : (
        <span>{getInitial(user)}</span>
      )}
    </div>
  );
}

export function TaxAiAvatar({ className = "" }: TaxAiAvatarProps) {
  return (
    <div className={`rounded-full flex items-center justify-center overflow-hidden ${className}`}>
      <Mark size={32} chip />
    </div>
  );
}
