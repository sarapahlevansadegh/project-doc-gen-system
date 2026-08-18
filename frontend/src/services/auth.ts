import { api } from "@/api/axios";
import type { LoginRequest, RegisterRequest, TokenResponse, User } from "@/types/auth";

export const authApi = {
  login: (payload: LoginRequest) =>
    api.post<TokenResponse>("/auth/login", payload).then((r) => r.data),

  register: (payload: RegisterRequest) =>
    api.post<User>("/auth/register", payload).then((r) => r.data),

  refresh: (refreshToken: string) =>
    api
      .post<TokenResponse>("/auth/refresh", { refresh_token: refreshToken })
      .then((r) => r.data),

  me: () => {
    return api.get<User>("/auth/me").then((r) => r.data);
  },
};
