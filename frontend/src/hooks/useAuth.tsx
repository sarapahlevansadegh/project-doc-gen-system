import {
  useState,
  useEffect,
  useCallback,
  createContext,
  useContext,
  type ReactNode,
} from "react";

import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import { authApi } from "@/services/auth";
import type { User, TokenResponse } from "@/types/auth";

interface AuthContextValue {
  user: User |null;
  isLoading: boolean;
  error: Error |null;

  login: (
    payload: {
      email: string;
      password: string;
    },
    options?: {
      onSuccess?: () => void;
    },
  ) => void;

  register: (
    payload: {
      email: string;
      password: string;
      full_name?: string;
      role?: string;
    },
    options?: {
      onSuccess?: () => void;
    },
  ) => void;

  logout: () => void;

  isLoggingIn: boolean;
  isRegistering: boolean;
}

const AuthContext = createContext<AuthContextValue |null>(null);

export function AuthProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [user, setUser] = useState<User |null>(null);

  const queryClient = useQueryClient();

  const token = localStorage.getItem("access_token");

  const {
    data,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["auth", "me"],

    queryFn: authApi.me,

    enabled: !!token,
    retry: false,
  });

  useEffect(() => {
    if (data) {
      setUser(data);
    }
  }, [data]);

  const loginMutation = useMutation({
    mutationFn: authApi.login,

    onSuccess: (tokens: TokenResponse) => {
      localStorage.setItem(
        "access_token",
        tokens.access_token,
      );

      localStorage.setItem(
        "refresh_token",
        tokens.refresh_token,
      );

      queryClient.invalidateQueries({
        queryKey: ["auth", "me"],
      });
    },
  });

  const registerMutation = useMutation({
    mutationFn: authApi.register,

    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["auth"],
      });
    },
  });

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");

    setUser(null);

    queryClient.clear();
  }, [queryClient]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        error: error as Error |null,

        login: (payload, options) => {
          loginMutation.mutate(payload, {
            onSuccess: () => {
              options?.onSuccess?.();
            },
          });
        },

        register: (payload, options) => {
          registerMutation.mutate(payload, {
            onSuccess: () => {
              options?.onSuccess?.();
            },
          });
        },

        logout,

        isLoggingIn: loginMutation.isPending,
        isRegistering: registerMutation.isPending,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error(
      "useAuth must be used within an AuthProvider",
    );
  }

  return context;
}
