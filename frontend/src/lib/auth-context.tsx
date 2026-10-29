"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  DEMO_STATE_STORAGE_KEY,
  authApi,
  getStoredAccessToken,
  setStoredAccessToken,
  toastProblemError,
} from "@/lib/api-client";
import { ROLE_LABELS_PT_BR } from "@/lib/formatters";
import type {
  LoginRequest,
  OrganizationResponse,
  UserResponse,
  UserRole,
} from "@/types/api";

interface StoredDemoMetadata {
  readonly demoPublicQuoteToken: string | null;
  readonly demoActiveWorkOrderId: string | null;
}

interface AuthContextValue {
  readonly user: UserResponse | null;
  readonly organization: OrganizationResponse | null;
  readonly isAuthenticated: boolean;
  readonly isLoading: boolean;
  readonly isSwitchingDemo: boolean;
  readonly demoPublicQuoteToken: string | null;
  readonly demoActiveWorkOrderId: string | null;
  readonly loginWithCredentials: (payload: LoginRequest) => Promise<void>;
  readonly loginWithDemoPersona: (
    persona: UserRole,
    options?: { readonly redirect?: boolean }
  ) => Promise<void>;
  readonly resetDemoData: () => Promise<void>;
  readonly logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function readStoredDemoMetadata(): StoredDemoMetadata {
  if (typeof window === "undefined") {
    return { demoPublicQuoteToken: null, demoActiveWorkOrderId: null };
  }
  try {
    const raw = window.localStorage.getItem(DEMO_STATE_STORAGE_KEY);
    if (!raw) {
      return { demoPublicQuoteToken: null, demoActiveWorkOrderId: null };
    }
    const parsed = JSON.parse(raw) as Partial<StoredDemoMetadata>;
    return {
      demoPublicQuoteToken:
        typeof parsed.demoPublicQuoteToken === "string"
          ? parsed.demoPublicQuoteToken
          : null,
      demoActiveWorkOrderId:
        typeof parsed.demoActiveWorkOrderId === "string"
          ? parsed.demoActiveWorkOrderId
          : null,
    };
  } catch {
    return { demoPublicQuoteToken: null, demoActiveWorkOrderId: null };
  }
}

function writeStoredDemoMetadata(meta: StoredDemoMetadata): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(DEMO_STATE_STORAGE_KEY, JSON.stringify(meta));
}

export function AuthProvider({
  children,
}: {
  readonly children: React.ReactNode;
}): React.JSX.Element {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [user, setUser] = useState<UserResponse | null>(null);
  const [organization, setOrganization] =
    useState<OrganizationResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSwitchingDemo, setIsSwitchingDemo] = useState<boolean>(false);
  const [demoMeta, setDemoMeta] = useState<StoredDemoMetadata>(() =>
    readStoredDemoMetadata()
  );

  useEffect(() => {
    let isMounted = true;
    const token = getStoredAccessToken();
    if (!token) {
      Promise.resolve().then(() => {
        if (isMounted) {
          setIsLoading(false);
        }
      });
      return () => {
        isMounted = false;
      };
    }

    authApi
      .me()
      .then((res) => {
        if (!isMounted) return;
        setUser(res.user);
        setOrganization(res.organization);
      })
      .catch(() => {
        if (!isMounted) return;
        setStoredAccessToken(null);
        setUser(null);
        setOrganization(null);
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const loginWithCredentials = useCallback(
    async (payload: LoginRequest): Promise<void> => {
      setIsSwitchingDemo(true);
      try {
        const res = await authApi.login(payload);
        setStoredAccessToken(res.access_token);
        setUser(res.user);
        setOrganization(res.organization);
        await queryClient.invalidateQueries();
        toast.success(`Bem-vindo(a), ${res.user.full_name}!`, {
          description: `${res.organization.name} • ${ROLE_LABELS_PT_BR[res.user.role]}`,
        });
        router.push(
          res.user.role === "OWNER" ? "/dashboard" : "/work-orders"
        );
      } catch (err) {
        toastProblemError(err, "Falha na autenticação");
        throw err;
      } finally {
        setIsSwitchingDemo(false);
      }
    },
    [queryClient, router]
  );

  const loginWithDemoPersona = useCallback(
    async (
      persona: UserRole,
      options?: { readonly redirect?: boolean }
    ): Promise<void> => {
      setIsSwitchingDemo(true);
      try {
        const res = await authApi.demoLogin({ persona });
        const nextMeta: StoredDemoMetadata = {
          demoPublicQuoteToken: res.demo_public_quote_token,
          demoActiveWorkOrderId: res.demo_active_work_order_id,
        };
        setDemoMeta(nextMeta);
        writeStoredDemoMetadata(nextMeta);

        if (persona === "PUBLIC_CLIENT") {
          toast.info("Abrindo Portal Público de Proposta do Cliente", {
            description:
              "Acesso via link seguro sem necessidade de senha (visão do cliente final).",
          });
          if (options?.redirect !== false) {
            router.push(`/p/${res.demo_public_quote_token}`);
          }
          return;
        }

        if (res.access_token && res.user) {
          setStoredAccessToken(res.access_token);
          setUser(res.user);
          setOrganization(res.organization);
          await queryClient.invalidateQueries();
          toast.success(
            `Modo Demo Ativado: ${ROLE_LABELS_PT_BR[persona]}`,
            {
              description: `${res.user.full_name} (${res.organization.name})`,
            }
          );
          if (options?.redirect !== false) {
            router.push(res.redirect_path);
          }
        }
      } catch (err) {
        toastProblemError(err, "Erro ao iniciar Modo Demo");
        throw err;
      } finally {
        setIsSwitchingDemo(false);
      }
    },
    [queryClient, router]
  );

  const resetDemoData = useCallback(async (): Promise<void> => {
    setIsSwitchingDemo(true);
    try {
      const res = await authApi.demoReset();
      const nextMeta: StoredDemoMetadata = {
        demoPublicQuoteToken: res.demo_public_quote_token,
        demoActiveWorkOrderId: res.demo_active_work_order_id,
      };
      setDemoMeta(nextMeta);
      writeStoredDemoMetadata(nextMeta);
      await queryClient.invalidateQueries();
      toast.success("Dados da Demo Restaurados com Sucesso!", {
        description: `${res.catalog_items_restored} SKUs Intelbras/WD Purple e ${res.quotes_restored} orçamentos de demonstração redefinidos.`,
      });
    } catch (err) {
      toastProblemError(err, "Erro ao restaurar dados da Demo");
      throw err;
    } finally {
      setIsSwitchingDemo(false);
    }
  }, [queryClient]);

  const logout = useCallback((): void => {
    setStoredAccessToken(null);
    setUser(null);
    setOrganization(null);
    queryClient.clear();
    toast.info("Sessão encerrada.");
    router.push("/login");
  }, [queryClient, router]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      organization,
      isAuthenticated: Boolean(user),
      isLoading,
      isSwitchingDemo,
      demoPublicQuoteToken: demoMeta.demoPublicQuoteToken,
      demoActiveWorkOrderId: demoMeta.demoActiveWorkOrderId,
      loginWithCredentials,
      loginWithDemoPersona,
      resetDemoData,
      logout,
    }),
    [
      user,
      organization,
      isLoading,
      isSwitchingDemo,
      demoMeta.demoPublicQuoteToken,
      demoMeta.demoActiveWorkOrderId,
      loginWithCredentials,
      loginWithDemoPersona,
      resetDemoData,
      logout,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth deve ser utilizado dentro de um AuthProvider.");
  }
  return ctx;
}
