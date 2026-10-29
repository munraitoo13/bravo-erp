"use client";

import React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Building2,
  CheckCircle2,
  ExternalLink,
  HardHat,
  KeyRound,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/lib/auth-context";

const loginSchema = z.object({
  email: z.string().email("Informe um e-mail corporativo válido."),
  password: z.string().min(1, "Informe sua senha de acesso."),
  organization_slug: z.string().optional(),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage(): React.JSX.Element {
  const {
    loginWithCredentials,
    loginWithDemoPersona,
    resetDemoData,
    isSwitchingDemo,
  } = useAuth();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "carlos.mendes@bravoseguranca.com.br",
      password: "BravoDemo@2026",
      organization_slug: "bravo-seguranca-demo",
    },
  });

  const onSubmit = async (values: LoginFormValues): Promise<void> => {
    await loginWithCredentials({
      email: values.email,
      password: values.password,
      organization_slug: values.organization_slug || null,
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-emerald-950 text-slate-100 flex flex-col justify-between p-4 sm:p-8">
      {/* Header */}
      <header className="max-w-6xl w-full mx-auto flex flex-wrap items-center justify-between gap-4 py-2">
        <div className="flex items-center gap-3">
          <div className="size-10 rounded-xl bg-emerald-500/20 border border-emerald-400/40 flex items-center justify-center text-emerald-400">
            <ShieldCheck className="size-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold tracking-tight text-white">
                BRAVO ERP
              </span>
              <Badge className="bg-emerald-500/20 text-emerald-300 border-emerald-400/30 text-xs">
                CFTV & Segurança Eletrônica
              </Badge>
            </div>
            <p className="text-xs text-slate-400">
              Engenharia Intelbras Multi-HD MHDX • IP NVD • WD Purple • Cofre de
              Garantias
            </p>
          </div>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isSwitchingDemo}
          onClick={() => void resetDemoData()}
          className="border-slate-700 bg-slate-900/80 text-slate-200 hover:bg-slate-800 hover:text-white"
        >
          <RefreshCw
            className={`size-3.5 mr-1.5 ${isSwitchingDemo ? "animate-spin" : ""}`}
          />
          Restaurar Dados da Demo
        </Button>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl w-full mx-auto my-auto py-8 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: 1-Click Recruiter Demo Mode */}
        <div className="lg:col-span-7 space-y-6">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/15 border border-emerald-400/30 px-3 py-1 text-xs font-medium text-emerald-300">
              <Sparkles className="size-3.5" />
              Modo Demonstração Instantânea (1-Click Recruiter Demo)
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
              Experimente o fluxo completo sem digitar senhas
            </h1>
            <p className="text-sm text-slate-300 leading-relaxed">
              Selecione qualquer uma das 3 personas abaixo para inspecionar a
              arquitetura Multi-Tenant, o motor de dimensionamento técnico CFTV,
              a reserva pessimista de estoque (<code className="text-emerald-300">SELECT ... FOR UPDATE</code>) e a
              segregação de custos/margens por perfil (RBAC).
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4">
            {/* Persona 1: Demo Owner */}
            <Card className="bg-slate-900/90 border-emerald-500/40 text-slate-100 shadow-xl">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="size-9 rounded-lg bg-emerald-500/20 border border-emerald-400/40 flex items-center justify-center text-emerald-300">
                      <Building2 className="size-5" />
                    </div>
                    <div>
                      <CardTitle className="text-base text-white">
                        1. Demo Proprietário / Gestor (Owner)
                      </CardTitle>
                      <CardDescription className="text-xs text-slate-400">
                        Carlos Eduardo Mendes • Bravo Segurança Eletrônica Ltda
                      </CardDescription>
                    </div>
                  </div>
                  <Badge className="bg-emerald-500 text-slate-950 font-semibold">
                    Acesso Total + Margens
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <ul className="text-xs text-slate-300 space-y-1">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="size-3.5 text-emerald-400 shrink-0" />
                    Visualiza preço de custo (<code className="text-emerald-300">cost_price_cents</code>), lucro bruto e margem percentual.
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="size-3.5 text-emerald-400 shrink-0" />
                    Calculadora de Dimensionamento CFTV (MHDX híbrido, HDs WD Purple, queda de tensão) e Radar de 11 Meses.
                  </li>
                </ul>
                <Button
                  type="button"
                  disabled={isSwitchingDemo}
                  onClick={() => void loginWithDemoPersona("OWNER")}
                  className="w-full h-10 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold"
                >
                  <Building2 className="size-4 mr-2" />
                  Entrar como Proprietário (Demo Owner)
                </Button>
              </CardContent>
            </Card>

            {/* Persona 2: Demo Technician */}
            <Card className="bg-slate-900/90 border-sky-500/40 text-slate-100 shadow-xl">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="size-9 rounded-lg bg-sky-500/20 border border-sky-400/40 flex items-center justify-center text-sky-300">
                      <HardHat className="size-5" />
                    </div>
                    <div>
                      <CardTitle className="text-base text-white">
                        2. Demo Técnico de Campo (Field Technician)
                      </CardTitle>
                      <CardDescription className="text-xs text-slate-400">
                        Rafael Oliveira Silva (Instalador) • Custos e margens ocultados no backend
                      </CardDescription>
                    </div>
                  </div>
                  <Badge className="bg-sky-500/20 text-sky-300 border-sky-400/30">
                    Mobile-First O.S.
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <ul className="text-xs text-slate-300 space-y-1">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="size-3.5 text-sky-400 shrink-0" />
                    Execução de Ordem de Serviço em campo: checklist interativo, upload de fotos e Intelbras Cloud P2P.
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="size-3.5 text-sky-400 shrink-0" />
                    Cofre de Números de Série (Serial Vault) exigindo registro de DVR, HD e câmeras antes de concluir a O.S.
                  </li>
                </ul>
                <Button
                  type="button"
                  disabled={isSwitchingDemo}
                  onClick={() => void loginWithDemoPersona("TECHNICIAN")}
                  className="w-full h-10 bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold"
                >
                  <HardHat className="size-4 mr-2" />
                  Entrar como Técnico de Campo (Demo Technician)
                </Button>
              </CardContent>
            </Card>

            {/* Persona 3: Demo Public Proposal */}
            <Card className="bg-slate-900/90 border-amber-500/40 text-slate-100 shadow-xl">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="size-9 rounded-lg bg-amber-500/20 border border-amber-400/40 flex items-center justify-center text-amber-300">
                      <ExternalLink className="size-5" />
                    </div>
                    <div>
                      <CardTitle className="text-base text-white">
                        3. Demo Proposta Pública do Cliente (Public Proposal)
                      </CardTitle>
                      <CardDescription className="text-xs text-slate-400">
                        Condomínio Residencial Jardim das Acácias • Link Público sem Login
                      </CardDescription>
                    </div>
                  </div>
                  <Badge className="bg-amber-500/20 text-amber-300 border-amber-400/30">
                    Aprovação em 1 Clique
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <ul className="text-xs text-slate-300 space-y-1">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="size-3.5 text-amber-400 shrink-0" />
                    Teste a aprovação comercial em 1 clique com trava pessimista de estoque (<code className="text-amber-300">SELECT ... FOR UPDATE</code>).
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="size-3.5 text-amber-400 shrink-0" />
                    Geração assíncrona de PDF via Transactional Outbox + WeasyPrint e verificação criptográfica SHA-256.
                  </li>
                </ul>
                <Button
                  type="button"
                  disabled={isSwitchingDemo}
                  onClick={() => void loginWithDemoPersona("PUBLIC_CLIENT")}
                  className="w-full h-10 bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold"
                >
                  <ExternalLink className="size-4 mr-2" />
                  Abrir Proposta Pública do Cliente (Demo Public Proposal)
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Right Column: Standard Credentials Login */}
        <div className="lg:col-span-5">
          <Card className="bg-white text-slate-900 border-slate-200 shadow-2xl">
            <CardHeader>
              <div className="flex items-center gap-2 text-emerald-700 text-xs font-semibold uppercase tracking-wider">
                <KeyRound className="size-4" />
                Acesso Corporativo Padrão
              </div>
              <CardTitle className="text-xl font-bold text-slate-900">
                Entrar com Credenciais
              </CardTitle>
              <CardDescription className="text-slate-600">
                Autenticação Argon2id + JWT com isolamento Multi-Tenant por organização.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form
                onSubmit={(e) => void handleSubmit(onSubmit)(e)}
                className="space-y-4"
              >
                <div className="space-y-1.5">
                  <Label htmlFor="email">E-mail Corporativo</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="nome@empresa.com.br"
                    {...register("email")}
                  />
                  {errors.email && (
                    <p className="text-xs text-red-600">{errors.email.message}</p>
                  )}
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="password">Senha</Label>
                  <Input
                    id="password"
                    type="password"
                    placeholder="••••••••••••"
                    {...register("password")}
                  />
                  {errors.password && (
                    <p className="text-xs text-red-600">
                      {errors.password.message}
                    </p>
                  )}
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="organization_slug">
                    Slug da Organização (Opcional)
                  </Label>
                  <Input
                    id="organization_slug"
                    type="text"
                    placeholder="bravo-seguranca-demo"
                    {...register("organization_slug")}
                  />
                </div>

                <Button
                  type="submit"
                  disabled={isSubmitting || isSwitchingDemo}
                  className="w-full h-10 bg-slate-900 hover:bg-slate-800 text-white font-semibold"
                >
                  {isSubmitting ? "Autenticando..." : "Acessar Plataforma"}
                </Button>

                <Separator className="my-3" />

                <div className="rounded-lg bg-slate-50 p-3 border border-slate-200 text-xs text-slate-600 space-y-1">
                  <p className="font-semibold text-slate-800">
                    Credenciais pré-preenchidas (Seed Demo):
                  </p>
                  <p>
                    <strong>Owner:</strong>{" "}
                    <code>carlos.mendes@bravoseguranca.com.br</code>
                  </p>
                  <p>
                    <strong>Técnico:</strong>{" "}
                    <code>rafael.silva@bravoseguranca.com.br</code>
                  </p>
                  <p>
                    <strong>Senha:</strong> <code>BravoDemo@2026</code>
                  </p>
                  <p>
                    <strong>Slug Org:</strong> <code>bravo-seguranca-demo</code>
                  </p>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      </main>

      {/* Footer */}
      <footer className="max-w-6xl w-full mx-auto text-center sm:text-left flex flex-col sm:flex-row items-center justify-between text-xs text-slate-400 border-t border-slate-800/80 pt-4">
        <span>
          Bravo ERP v1.0 • FastAPI + SQLAlchemy 2.0 Async + Taskiq + Next.js App
          Router
        </span>
        <span>Contratos de Erro RFC 7807 Problem+JSON & Trace Correlation-ID</span>
      </footer>
    </div>
  );
}
