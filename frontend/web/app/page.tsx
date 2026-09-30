"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { onAuthStateChanged, User } from "firebase/auth";
import { api, ApiError } from "./lib/api";
import { authenticate, firebaseAuth, logout } from "./lib/auth";

type Clinic = { id_clinica: number; nome: string; responsavel?: string };
type Patient = {
  id_paciente: number;
  nome: string;
  telefone?: string;
  cpf_mascarado: string;
  anamnese_status?: string;
  ativo?: boolean;
  aceito_em?: string;
};
type PatientResult = { items: Patient[]; total: number; page: number; page_size: number };
type AnamnesisStatus = "PENDENTE" | "PENDENTE_APROVACAO" | "VENCIDA" | "ATUALIZADA";
type ActiveFilter = "true" | "false" | "all";
type ClinicPanel = {
  pacientes_ativos: number;
  pendentes_preenchimento: number;
  pendentes_aprovacao: number;
  atualizadas: number;
  vencidas: number;
  prioridades: Patient[];
};
type Question = {
  id_pergunta: number;
  texto: string;
  tipo: "BOOLEAN" | "TEXT" | "SINGLE_CHOICE";
  obrigatoria: boolean;
  parent_question_id?: number;
  show_when_value?: string;
  options?: string[];
};
type FormDefinition = {
  id_formulario: number;
  nome: string;
  versao: number;
  termos_texto: string;
  modo_teste?: boolean;
  uso_clinico?: boolean;
  questions: Question[];
};
type HistoryItem = {
  id_anamnese_versao: number;
  numero_versao: number;
  aceito_em: string;
  status_aprovacao: string;
  nome_profissional?: string;
  cro_profissional?: string;
  aprovado_em?: string;
};
type Alert = { codigo: string; descricao: string };
type Profile = {
  id_paciente: number;
  id_clinica: number;
  nome: string;
  telefone?: string;
  email?: string;
  data_nascimento: string;
  plano_odontologico?: string;
  endereco?: string;
  anamnese_status: string;
  alerts?: Alert[];
};
type RemoteLink = { url: string; expires_at: string };
type Identity = {
  id_usuario: number;
  nome: string;
  email: string;
  troca_senha_obrigatoria: boolean;
  perfis: string[];
  permissoes: string[];
};
type TeamMember = {
  id_usuario: number;
  nome: string;
  email: string;
  ativo: boolean;
  troca_senha_obrigatoria: boolean;
  profile_code: "RECEPCAO" | "FINANCEIRO";
  perfil_nome: string;
  clinic_ids: number[];
};
type TeamResult = { items: TeamMember[]; ativos: number; limite: number };
type Doctor = {
  id_doutor: number;
  id_doutor_clinica: number | null;
  nome_doutor: string;
  especialidade: string | null;
  cro: string | null;
  cro_estado: string | null;
  percentual_repasse: number | null;
  flag_ativo: boolean;
  total_consultas: number;
};
type DoctorResult = { items: Doctor[]; total: number; page: number; page_size: number };
type DoctorDetail = Doctor & {
  id_clinica: number;
  data_inicio: string | null;
  data_fim: string | null;
};
type PatientPayload = {
  nome: FormDataEntryValue | null;
  cpf: FormDataEntryValue | null;
  data_nascimento: string;
  sexo: FormDataEntryValue | null;
  telefone: string | null;
  email: string | null;
  endereco: string | null;
  plano_odontologico: string | null;
  idempotency_key: string;
  responsavel?: {
    nome: FormDataEntryValue | null;
    cpf: FormDataEntryValue | null;
    telefone: FormDataEntryValue | null;
    email: string | null;
    parentesco: FormDataEntryValue | null;
  };
};
type Consultation = {
  id_consulta: number;
  id_clinica: number;
  id_paciente: number | null;
  id_doutor: number | null;
  nome_paciente: string | null;
  nome_doutor: string | null;
  especialidade: string | null;
  data_consulta: string | null;
  status: string | null;
  valor_total: number | null;
  total_itens: number;
  soma_itens: number | null;
  flag_paciente_localizado: boolean | null;
  divergencia_valor: boolean;
};
type ConsultationResult = { items: Consultation[]; total: number; page: number; page_size: number };
type ConsultationProcedure = {
  id_consulta_procedimento: number;
  nome_procedimento: string | null;
  elemento_dental: string | null;
  descricao: string | null;
  valor_consulta: number | null;
};
type ConsultationDetail = Consultation & {
  tipo_match_paciente: string | null;
  nome_paciente_origem: string | null;
  itens: ConsultationProcedure[];
};
type NavigationScreen = "overview" | "patients" | "anamneses" | "team" | "doctors" | "consultations";

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [screen, setScreen] = useState("login");
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [clinic, setClinic] = useState<Clinic | null>(null);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [patientToken, setPatientToken] = useState("");
  const [form, setForm] = useState<FormDefinition | null>(null);
  const [lockOutcome, setLockOutcome] = useState<"completed" | "cancelled">(
    "completed",
  );
  const [profile, setProfile] = useState<Profile | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [remoteToken, setRemoteToken] = useState("");
  const [remoteMode, setRemoteMode] = useState(false);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [team, setTeam] = useState<TeamResult | null>(null);
  const [patientResult, setPatientResult] = useState<PatientResult>({ items: [], total: 0, page: 1, page_size: 25 });
  const [patientCache, setPatientCache] = useState<Record<string, PatientResult>>({});
  const [panel, setPanel] = useState<ClinicPanel | null>(null);
  const [panelCache, setPanelCache] = useState<Record<number, ClinicPanel>>({});
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>("true");
  const [patientPage, setPatientPage] = useState(1);
  const [anamnesisStatus, setAnamnesisStatus] = useState<AnamnesisStatus>("PENDENTE");
  const [transitioning, setTransitioning] = useState(false);
  const [doctors, setDoctors] = useState<DoctorResult>({ items: [], total: 0, page: 1, page_size: 25 });
  const [doctorCache, setDoctorCache] = useState<Record<string, DoctorResult>>({});
  const [doctorPage, setDoctorPage] = useState(1);
  const [doctorSearch, setDoctorSearch] = useState("");
  const [doctorActiveFilter, setDoctorActiveFilter] = useState<ActiveFilter>("all");
  const [doctorDetail, setDoctorDetail] = useState<DoctorDetail | null>(null);
  const [consultations, setConsultations] = useState<ConsultationResult>({ items: [], total: 0, page: 1, page_size: 25 });
  const [consultationCache, setConsultationCache] = useState<Record<string, ConsultationResult>>({});
  const [consultationPage, setConsultationPage] = useState(1);
  const [consultationSearch, setConsultationSearch] = useState("");
  const [consultationDateFrom, setConsultationDateFrom] = useState("");
  const [consultationDateTo, setConsultationDateTo] = useState("");
  const [consultationDoctorId, setConsultationDoctorId] = useState<number | null>(null);
  const [consultationDetail, setConsultationDetail] = useState<ConsultationDetail | null>(null);

  useEffect(() => {
    if (window.location.pathname === "/anamnese/responder") {
      const token =
        new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
      // React executes effects twice in development. After the first pass the
      // fragment is intentionally removed, so never replace the captured token
      // with an empty value on the second pass.
      if (token) setRemoteToken(token);
      setRemoteMode(true);
      if (token)
        window.history.replaceState(null, "", window.location.pathname);
      setReady(true);
      return;
    }
    try {
      return onAuthStateChanged(firebaseAuth(), (current) => {
        setUser(current);
        setReady(true);
        if (!current) setScreen("login");
      });
    } catch (err) {
      queueMicrotask(() => {
        setReady(true);
        setError(err instanceof Error ? err.message : "Configuração inválida");
      });
      return undefined;
    }
  }, []);
  async function run<T>(task: () => Promise<T>, done: (value: T) => void) {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      done(await task());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro inesperado");
    } finally {
      setLoading(false);
    }
  }
  async function enter(email: string, password: string, register: boolean) {
    await run(
      async () => {
        await authenticate(email, password, register);
        let me: Identity | null = null;
        try {
          me = await api<Identity>("/me");
        } catch (err) {
          if (!(err instanceof ApiError) || err.code !== "SETUP_REQUIRED")
            throw err;
        }
        if (me?.troca_senha_obrigatoria)
          return { me, available: [] as Clinic[] };
        const available = me ? await api<Clinic[]>("/me/clinicas") : [];
        return { me, available };
      },
      ({ me, available }) => {
        setIdentity(me);
        setClinics(available);
        setScreen(
          me?.troca_senha_obrigatoria
            ? "changePassword"
            : available.length
              ? "clinics"
              : "setup",
        );
      },
    );
  }
  function patientCacheKey(item: Clinic, term: string, active: ActiveFilter, page: number, status?: AnamnesisStatus) {
    return `${item.id_clinica}:${term.trim().toLowerCase()}:${active}:${status || "todos"}:${page}`;
  }
  async function loadPatientList(item: Clinic, term: string, active: ActiveFilter, page: number, status?: AnamnesisStatus) {
    const key = patientCacheKey(item, term, active, page, status);
    const cached = patientCache[key];
    if (cached) {
      setPatientResult(cached);
      setPatients(cached.items);
    }
    const params = new URLSearchParams({ search: term, page: String(page), page_size: "25" });
    if (active !== "all") params.set("active", active);
    if (status) params.set("anamnesis_status", status);
    await run(
      () => api<PatientResult>(`/clinicas/${item.id_clinica}/pacientes?${params}`),
      (result) => {
        setPatientResult(result);
        setPatients(result.items);
        setPatientCache((current) => ({ ...current, [key]: result }));
      },
    );
  }
  async function loadPatients(term = search, page = patientPage) {
    if (!clinic) return;
    await loadPatientList(clinic, term, activeFilter, page);
  }
  async function loadPanelFor(item: Clinic) {
    if (panelCache[item.id_clinica]) setPanel(panelCache[item.id_clinica]);
    await run(
      () => api<ClinicPanel>(`/clinicas/${item.id_clinica}/painel`),
      (result) => {
        setPanel(result);
        setPanelCache((current) => ({ ...current, [item.id_clinica]: result }));
      },
    );
  }
  function chooseClinic(item: Clinic) {
    setClinic(item);
    setScreen("overview");
    setPatientPage(1);
    setTimeout(() => void loadPanelFor(item), 0);
  }
  async function beginPatientMode(id: number) {
    if (!clinic) return;
    await run(
      () =>
        api<{ token: string }>(`/clinicas/${clinic.id_clinica}/modo-paciente`, {
          method: "POST",
          body: JSON.stringify({ patient_id: id }),
        }),
      async (result) => {
        setPatientToken(result.token);
        try {
          setForm(
            await api<FormDefinition>(
              "/modo-paciente/formulario",
              {},
              result.token,
            ),
          );
          setScreen("patientMode");
        } catch (err) {
          try {
            await api(
              "/modo-paciente/cancelar",
              { method: "POST" },
              result.token,
            );
          } catch {}
          setPatientToken("");
          setError(
            err instanceof Error ? err.message : "Formulário indisponível",
          );
        }
      },
    );
  }
  async function cancelPatientMode() {
    if (patientToken) {
      try {
        await api("/modo-paciente/cancelar", { method: "POST" }, patientToken);
      } catch {}
    }
    setPatientToken("");
    setForm(null);
    setLockOutcome("cancelled");
    setScreen("locked");
  }
  async function openProfile(id: number) {
    if (!clinic) return;
    await run(
      async () => {
        const [patientProfile, patientHistory] = await Promise.all([
          api<Profile>(
          `/clinicas/${clinic.id_clinica}/pacientes/${id}`,
          ),
          api<HistoryItem[]>(
          `/clinicas/${clinic.id_clinica}/pacientes/${id}/anamnese/historico`,
          ),
        ]);
        return { profile: patientProfile, history: patientHistory };
      },
      (value) => {
        setProfile(value.profile);
        setHistory(value.history);
      },
    );
  }
  async function leave() {
    await logout();
    setError("");
    setNotice("");
    setIdentity(null);
    setTeam(null);
    setClinic(null);
    setClinics([]);
    setPatients([]);
    setPatientResult({ items: [], total: 0, page: 1, page_size: 25 });
    setPatientCache({});
    setPanel(null);
    setPanelCache({});
    setProfile(null);
    setHistory([]);
    setSearch("");
    setDoctors({ items: [], total: 0, page: 1, page_size: 25 });
    setDoctorCache({});
    setDoctorPage(1);
    setDoctorSearch("");
    setDoctorActiveFilter("all");
    setDoctorDetail(null);
    setConsultations({ items: [], total: 0, page: 1, page_size: 25 });
    setConsultationCache({});
    setConsultationPage(1);
    setConsultationSearch("");
    setConsultationDateFrom("");
    setConsultationDateTo("");
    setConsultationDoctorId(null);
    setConsultationDetail(null);
    setScreen("login");
  }
  async function loadDoctorList(targetClinic: typeof clinic, search: string, active: ActiveFilter, page: number) {
    if (!targetClinic) return;
    const cacheKey = `${targetClinic.id_clinica}:${search}:${active}:${page}`;
    if (doctorCache[cacheKey]) { setDoctors(doctorCache[cacheKey]); return; }
    await run(
      () => api<DoctorResult>(`/clinicas/${targetClinic.id_clinica}/doutores?search=${encodeURIComponent(search)}&ativo=${active}&page=${page}&page_size=25`),
      (result) => {
        setDoctors(result);
        setDoctorCache((prev) => ({ ...prev, [cacheKey]: result }));
      },
    );
  }
  async function openDoctors() {
    if (!clinic) return;
    await loadDoctorList(clinic, doctorSearch, doctorActiveFilter, doctorPage);
    setScreen("doctors");
  }
  async function loadConsultationList(targetClinic: typeof clinic, search: string, dateFrom: string, dateTo: string, doctorId: number | null, page: number) {
    if (!targetClinic) return;
    const cacheKey = `${targetClinic.id_clinica}:${search}:${dateFrom}:${dateTo}:${doctorId ?? ""}:${page}`;
    if (consultationCache[cacheKey]) { setConsultations(consultationCache[cacheKey]); return; }
    const params = new URLSearchParams({ search, page: String(page), page_size: "25" });
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    if (doctorId !== null) params.set("doctor_id", String(doctorId));
    await run(
      () => api<ConsultationResult>(`/clinicas/${targetClinic.id_clinica}/consultas?${params}`),
      (result) => {
        setConsultations(result);
        setConsultationCache((prev) => ({ ...prev, [cacheKey]: result }));
      },
    );
  }
  async function openConsultations() {
    if (!clinic) return;
    await loadConsultationList(clinic, consultationSearch, consultationDateFrom, consultationDateTo, consultationDoctorId, consultationPage);
    setScreen("consultations");
  }
  async function openTeam() {
    await run(
      () => api<TeamResult>("/equipe"),
      (result) => {
        setTeam(result);
        setScreen("team");
      },
    );
  }
  if (!ready) return <Loading />;
  if (remoteMode) return <RemoteAnamnesis token={remoteToken} />;
  if (screen === "login")
    return <Login error={error} loading={loading} onSubmit={enter} />;
  if (screen === "changePassword")
    return (
      <PasswordChange
        email={user?.email || identity?.email || ""}
        error={error}
        loading={loading}
        onSubmit={(password) =>
          run(
            async () => {
              await api("/me/alterar-senha", {
                method: "POST",
                body: JSON.stringify({ nova_senha: password }),
              });
              // Firebase revokes the ID token after the Admin SDK changes the
              // password. Establish a fresh client session with the new
              // credential before requesting identity and clinics.
              await authenticate(
                user?.email || identity?.email || "",
                password,
                false,
              );
              return {
                me: await api<Identity>("/me"),
                available: await api<Clinic[]>("/me/clinicas"),
              };
            },
            (value) => {
              setIdentity(value.me);
              setClinics(value.available);
              setScreen("clinics");
            },
          )
        }
        onExit={leave}
      />
    );
  if (screen === "setup")
    return (
      <Setup
        loading={loading}
        error={error}
        onCreate={(name) =>
          run(
            () =>
              api("/setup", {
                method: "POST",
                body: JSON.stringify({ nome: name }),
              }),
            () => setScreen("createClinic"),
          )
        }
        onExit={leave}
      />
    );
  if (screen === "createClinic")
    return (
      <ClinicCreate
        loading={loading}
        error={error}
        onCreate={(payload) =>
          run(
            () =>
              api<Clinic>("/clinicas", {
                method: "POST",
                body: JSON.stringify(payload),
              }),
            (created) => {
              setClinics([...clinics, created]);
              chooseClinic(created);
            },
          )
        }
        onExit={leave}
      />
    );
  if (screen === "clinics")
    return (
      <ClinicPicker
        clinics={clinics}
        canCreate={Boolean(identity?.permissoes.includes("CLINIC_MANAGE"))}
        onChoose={chooseClinic}
        onCreate={() => setScreen("createClinic")}
        onExit={leave}
      />
    );
  if (screen === "patientMode" && form)
    return (
      <PatientMode
        form={form}
        error={error}
        loading={loading}
        onSubmit={(payload) =>
          run(
            () =>
              api(
                "/modo-paciente/anamnese",
                { method: "POST", body: JSON.stringify(payload) },
                patientToken,
              ),
            () => {
              setPatientToken("");
              setForm(null);
              setLockOutcome("completed");
              setScreen("locked");
            },
          )
        }
        onCancel={() => void cancelPatientMode()}
      />
    );
  if (screen === "locked")
    return <Locked outcome={lockOutcome} onUnlock={() => void leave()} />;
  const navigate = (destination: NavigationScreen) => {
    if (destination === "team") {
      void openTeam();
      return;
    }
    if (destination === "doctors") {
      void openDoctors();
      return;
    }
    if (destination === "consultations") {
      void openConsultations();
      return;
    }
    setTransitioning(true);
    window.setTimeout(() => {
      setScreen(destination);
      if (clinic && destination === "overview") void loadPanelFor(clinic);
      if (clinic && destination === "patients") void loadPatientList(clinic, search, activeFilter, patientPage);
      if (clinic && destination === "anamneses") {
        void loadPanelFor(clinic);
        void loadPatientList(clinic, "", "true", 1, anamnesisStatus);
      }
      window.setTimeout(() => setTransitioning(false), 120);
    }, 0);
  };
  if (screen === "team" && team)
    return (
      <TeamPage
        user={user}
        identity={identity}
        clinic={clinic}
        clinics={clinics}
        initial={team}
        error={error}
        loading={loading}
        onNavigate={navigate}
        onClinicSelect={chooseClinic}
        onClinics={() => setScreen("clinics")}
        onLogout={leave}
        run={run}
      />
    );
  if (screen === "consultations")
    return (
      <ConsultasPage
        user={user}
        identity={identity}
        clinic={clinic}
        clinics={clinics}
        result={consultations}
        search={consultationSearch}
        setSearch={setConsultationSearch}
        dateFrom={consultationDateFrom}
        setDateFrom={setConsultationDateFrom}
        dateTo={consultationDateTo}
        setDateTo={setConsultationDateTo}
        doctorId={consultationDoctorId}
        page={consultationPage}
        detail={consultationDetail}
        error={error}
        loading={loading}
        onNavigate={navigate}
        onClinicSelect={chooseClinic}
        onClinics={() => setScreen("clinics")}
        onLogout={leave}
        onSearch={() => {
          setConsultationCache({});
          setConsultationPage(1);
          void loadConsultationList(clinic, consultationSearch, consultationDateFrom, consultationDateTo, consultationDoctorId, 1);
        }}
        onDoctorFilter={(id) => {
          setConsultationDoctorId(id);
          setConsultationCache({});
          setConsultationPage(1);
          void loadConsultationList(clinic, consultationSearch, consultationDateFrom, consultationDateTo, id, 1);
        }}
        onPage={(page) => {
          setConsultationPage(page);
          void loadConsultationList(clinic, consultationSearch, consultationDateFrom, consultationDateTo, consultationDoctorId, page);
        }}
        onDetail={async (id) => {
          if (!clinic) return;
          await run(
            () => api<ConsultationDetail>(`/clinicas/${clinic.id_clinica}/consultas/${id}`),
            (d) => setConsultationDetail(d),
          );
        }}
        onCloseDetail={() => setConsultationDetail(null)}
      />
    );
  if (screen === "doctors")
    return (
      <DoctorsPage
        user={user}
        identity={identity}
        clinic={clinic}
        clinics={clinics}
        result={doctors}
        search={doctorSearch}
        setSearch={setDoctorSearch}
        activeFilter={doctorActiveFilter}
        page={doctorPage}
        detail={doctorDetail}
        error={error}
        loading={loading}
        onNavigate={navigate}
        onClinicSelect={chooseClinic}
        onClinics={() => setScreen("clinics")}
        onLogout={leave}
        onSearch={() => {
          setDoctorCache({});
          setDoctorPage(1);
          void loadDoctorList(clinic, doctorSearch, doctorActiveFilter, 1);
        }}
        onActiveFilter={(value) => {
          setDoctorActiveFilter(value);
          setDoctorCache({});
          setDoctorPage(1);
          void loadDoctorList(clinic, doctorSearch, value, 1);
        }}
        onPage={(page) => {
          setDoctorPage(page);
          void loadDoctorList(clinic, doctorSearch, doctorActiveFilter, page);
        }}
        onDetail={async (id) => {
          if (!clinic) return;
          await run(
            () => api<DoctorDetail>(`/clinicas/${clinic.id_clinica}/doutores/${id}`),
            (d) => setDoctorDetail(d),
          );
        }}
        onCloseDetail={() => setDoctorDetail(null)}
      />
    );
  const dashboardScreen: Exclude<NavigationScreen, "team" | "doctors" | "consultations"> =
    screen === "overview" || screen === "anamneses" ? screen : "patients";
  return (
    <Dashboard
      view={dashboardScreen}
      user={user}
      identity={identity}
      clinic={clinic}
      clinics={clinics}
      patients={patients}
      patientResult={patientResult}
      panel={panel}
      activeFilter={activeFilter}
      patientPage={patientPage}
      anamnesisStatus={anamnesisStatus}
      search={search}
      setSearch={setSearch}
      error={error}
      notice={notice}
      loading={loading}
      transitioning={transitioning}
      onSearch={() => loadPatients(search)}
      onActiveFilter={(value) => {
        if (!clinic) return;
        setActiveFilter(value);
        setPatientPage(1);
        void loadPatientList(clinic, search, value, 1);
      }}
      onPatientPage={(page) => {
        if (!clinic) return;
        setPatientPage(page);
        void loadPatientList(clinic, search, activeFilter, page);
      }}
      onAnamnesisStatus={(status) => {
        if (!clinic) return;
        setAnamnesisStatus(status);
        void loadPatientList(clinic, "", "true", 1, status);
      }}
      onClinic={() => setScreen("clinics")}
      onNavigate={navigate}
      onClinicSelect={chooseClinic}
      onLogout={leave}
      onNew={() => setScreen("newPatient")}
      onCancelNew={() => setScreen("patients")}
      newPatient={screen === "newPatient"}
      onPatientMode={beginPatientMode}
      onProfile={openProfile}
      profile={profile}
      history={history}
      onCloseProfile={() => setProfile(null)}
      onCreated={() => {
        setPatientCache({});
        setPanelCache({});
        setScreen("patients");
        if (!clinic) return;
        void loadPatientList(clinic, search, activeFilter, 1).then(() =>
          setNotice("Paciente cadastrado com sucesso."),
        );
      }}
      onDataChanged={() => {
        setPatientCache({});
        setPanelCache({});
        if (clinic) {
          if (dashboardScreen === "overview") void loadPanelFor(clinic);
          else if (dashboardScreen === "anamneses") void loadPatientList(clinic, "", "true", 1, anamnesisStatus);
          else void loadPatientList(clinic, search, activeFilter, patientPage);
        }
      }}
      run={run}
    />
  );
}

function PasswordChange({
  email,
  error,
  loading,
  onSubmit,
  onExit,
}: {
  email: string;
  error: string;
  loading: boolean;
  onSubmit: (password: string) => void;
  onExit: () => void;
}) {
  const [p1, setP1] = useState("");
  const [p2, setP2] = useState("");
  const [localError, setLocalError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  return (
    <Centered
      title="Crie sua senha pessoal"
      subtitle={`Primeiro acesso de ${email}. A senha temporária não poderá continuar sendo usada.`}
    >
      <form
        className="password-change-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (p1.length < 8) {
            setLocalError("Use pelo menos 8 caracteres.");
            return;
          }
          if (p1 !== p2) {
            setLocalError("As senhas não coincidem.");
            return;
          }
          setLocalError("");
          onSubmit(p1);
        }}
      >
        <div className="password-fields">
          <label>
            Nova senha
            <input
              type={showPassword ? "text" : "password"}
              value={p1}
              onChange={(e) => setP1(e.target.value)}
              minLength={8}
              required
              autoComplete="new-password"
            />
          </label>
          <label>
            Confirme a nova senha
            <input
              type={showPassword ? "text" : "password"}
              value={p2}
              onChange={(e) => setP2(e.target.value)}
              minLength={8}
              required
              autoComplete="new-password"
            />
          </label>
        </div>
        <div className="password-help">
          <span>Use pelo menos 8 caracteres.</span>
          <label>
            <input type="checkbox" checked={showPassword} onChange={(event) => setShowPassword(event.target.checked)}/>
            Mostrar senhas
          </label>
        </div>
        {(localError || error) && (
          <div className="error-box" role="alert">
            {localError || error}
          </div>
        )}
        <button className="primary-button wide" disabled={loading}>
          {loading ? "Alterando…" : "Salvar nova senha"}
        </button>
        <button type="button" className="link-button wide" onClick={onExit}>
          Sair
        </button>
      </form>
    </Centered>
  );
}

function Login({
  error,
  loading,
  onSubmit,
}: {
  error: string;
  loading: boolean;
  onSubmit: (e: string, p: string, r: boolean) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const button = (event.nativeEvent as SubmitEvent)
      .submitter as HTMLButtonElement | null;
    onSubmit(email.trim(), password, button?.value === "register");
  }
  return (
    <main className="auth-page">
      <section className="auth-visual">
        <div className="brand light">
          <span className="brand-mark">B</span>
          <span>Billing Control</span>
        </div>
        <div>
          <p className="eyebrow pale">GESTÃO ODONTOLÓGICA</p>
          <h1>
            Mais cuidado.
            <br />
            Menos burocracia.
          </h1>
          <p>
            Pacientes, anamneses e alertas clínicos organizados com segurança.
          </p>
        </div>
        <small>Dados isolados por clínica • Acesso individual</small>
      </section>
      <section className="auth-form">
        <form onSubmit={submit}>
          <p className="eyebrow">ACESSO SEGURO</p>
          <h2>Entre na sua conta</h2>
          <p className="subtitle">Use o e-mail cadastrado pela sua clínica.</p>
          <label>
            E-mail
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="voce@clinica.com"
            />
          </label>
          <label>
            Senha
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Sua senha"
            />
          </label>
          {error && (
            <div className="error-box" role="alert">
              {error}
            </div>
          )}
          <button
            type="submit"
            value="login"
            className="primary-button wide"
            disabled={loading}
          >
            {loading ? "Entrando…" : "Entrar"}
          </button>
          <button
            type="submit"
            value="register"
            className="link-button"
            disabled={loading}
          >
            Criar conta de proprietário
          </button>
        </form>
      </section>
    </main>
  );
}
function Setup({
  loading,
  error,
  onCreate,
  onExit,
}: {
  loading: boolean;
  error: string;
  onCreate: (n: string) => void;
  onExit: () => void;
}) {
  const [name, setName] = useState("");
  return (
    <Centered
      title="Configure sua organização"
      subtitle="Ela reunirá seus usuários e até três clínicas."
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onCreate(name);
        }}
        className="stack"
      >
        <label>
          Nome da organização
          <input
            required
            minLength={2}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ex.: Grupo Sorriso"
          />
        </label>
        {error && <div className="error-box">{error}</div>}
        <button className="primary-button" disabled={loading}>
          Criar organização
        </button>
        <button type="button" className="link-button" onClick={onExit}>
          Sair
        </button>
      </form>
    </Centered>
  );
}
function ClinicCreate({
  loading,
  error,
  onCreate,
  onExit,
}: {
  loading: boolean;
  error: string;
  onCreate: (p: Record<string, string | null>) => void;
  onExit: () => void;
}) {
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const d = new FormData(e.currentTarget);
    onCreate({
      nome: String(d.get("nome")),
      razao_social: String(d.get("razao")),
      cnpj_cpf: String(d.get("documento")),
      email: String(d.get("email")),
      telefone: String(d.get("telefone") || "") || null,
      endereco: String(d.get("endereco") || "") || null,
      responsavel: String(d.get("responsavel") || "") || null,
      cro_responsavel: String(d.get("cro") || "") || null,
    });
  }
  return (
    <Centered
      title="Cadastre sua clínica"
      subtitle="Você poderá adicionar até três clínicas à organização."
    >
      <form className="form-grid" onSubmit={submit}>
        <label className="span-2">
          Nome da clínica
          <input name="nome" required />
        </label>
        <label className="span-2">
          Razão social
          <input name="razao" required />
        </label>
        <label>
          CPF ou CNPJ
          <input name="documento" required />
        </label>
        <label>
          E-mail
          <input name="email" type="email" required />
        </label>
        <label>
          Telefone
          <input name="telefone" />
        </label>
        <label>
          Responsável
          <input name="responsavel" />
        </label>
        <label>
          CRO do responsável
          <input name="cro" />
        </label>
        <label className="span-2">
          Endereço
          <input name="endereco" />
        </label>
        {error && <div className="error-box span-2">{error}</div>}
        <div className="modal-actions span-2">
          <button type="button" className="ghost-button" onClick={onExit}>
            Sair
          </button>
          <button className="primary-button" disabled={loading}>
            Cadastrar clínica
          </button>
        </div>
      </form>
    </Centered>
  );
}
function ClinicPicker({
  clinics,
  canCreate,
  onChoose,
  onCreate,
  onExit,
}: {
  clinics: Clinic[];
  canCreate: boolean;
  onChoose: (c: Clinic) => void;
  onCreate: () => void;
  onExit: () => void;
}) {
  return (
    <Centered
      title="Selecione a clínica"
      subtitle="Todo o contexto seguinte ficará restrito à clínica escolhida."
    >
      <div className="clinic-grid">
        {clinics.map((c) => (
          <button
            key={c.id_clinica}
            className="clinic-card"
            onClick={() => onChoose(c)}
          >
            <span className="clinic-icon">+</span>
            <strong>{c.nome}</strong>
            <small>{c.responsavel || "Clínica odontológica"}</small>
          </button>
        ))}
        {canCreate && clinics.length < 3 && (
          <button className="clinic-card add" onClick={onCreate}>
            <span className="clinic-icon">+</span>
            <strong>Adicionar clínica</strong>
            <small>Até três por organização</small>
          </button>
        )}
      </div>
      <button className="link-button" onClick={onExit}>
        Sair da conta
      </button>
    </Centered>
  );
}
function Centered({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <main className="center-page">
      <div className="center-card">
        <div className="brand dark">
          <span className="brand-mark">B</span>
          <span>Billing Control</span>
        </div>
        <h1>{title}</h1>
        <p className="subtitle">{subtitle}</p>
        {children}
      </div>
    </main>
  );
}

function AppSidebar({
  current,
  identity,
  clinic,
  clinics,
  onNavigate,
  onClinicSelect,
  onClinics,
}: {
  current: NavigationScreen;
  identity: Identity | null;
  clinic: Clinic | null;
  clinics: Clinic[];
  onNavigate: (screen: NavigationScreen) => void;
  onClinicSelect: (clinic: Clinic) => void;
  onClinics: () => void;
}) {
  const canManageTeam = Boolean(identity?.permissoes.includes("USER_MANAGE"));
  const canReadPatients = Boolean(identity?.permissoes.includes("PATIENT_READ"));
  const canReadAnamnesis = Boolean(identity?.permissoes.includes("ANAMNESIS_READ"));
  const canReadDoctors = Boolean(identity?.permissoes.includes("DOCTOR_READ"));
  const canReadConsultations = Boolean(identity?.permissoes.includes("CONSULTATION_READ"));
  const item = (screen: NavigationScreen, icon: string, label: string) => (
    <button
      type="button"
      className={current === screen ? "active" : undefined}
      aria-current={current === screen ? "page" : undefined}
      onClick={() => onNavigate(screen)}
    >
      <span className="nav-icon" aria-hidden="true">{icon}</span>
      <span className="nav-label">{label}</span>
    </button>
  );
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">B</span>
        <span className="brand-label">Billing Control</span>
      </div>
      <div className="clinic-switcher">
        <label htmlFor="clinic-selector">Clínica atual</label>
        <select
          id="clinic-selector"
          value={clinic?.id_clinica || ""}
          onChange={(event) => {
            const selected = clinics.find(
              (candidate) => candidate.id_clinica === Number(event.target.value),
            );
            if (selected) onClinicSelect(selected);
          }}
        >
          {clinics.map((candidate) => (
            <option key={candidate.id_clinica} value={candidate.id_clinica}>
              {candidate.nome}
            </option>
          ))}
        </select>
      </div>
      <nav aria-label="Navegação principal">
        {canReadPatients && item("overview", "⌂", "Visão geral")}
        {canReadPatients && item("patients", "♙", "Pacientes")}
        {canReadAnamnesis && item("anamneses", "✚", "Anamneses")}
        {canReadDoctors && item("doctors", "♞", "Doutores")}
        {canReadConsultations && item("consultations", "✦", "Consultas")}
        {canManageTeam && item("team", "♧", "Equipe")}
      </nav>
      {identity?.permissoes.includes("CLINIC_MANAGE") && (
        <button type="button" className="sidebar-clinic-action" onClick={onClinics}>
          <span aria-hidden="true">↔</span>
          <span className="nav-label">Gerenciar clínicas</span>
        </button>
      )}
    </aside>
  );
}

function TeamPage({
  user,
  identity,
  clinic,
  clinics,
  initial,
  error,
  loading,
  onNavigate,
  onClinicSelect,
  onClinics,
  onLogout,
  run,
}: {
  user: User | null;
  identity: Identity | null;
  clinic: Clinic | null;
  clinics: Clinic[];
  initial: TeamResult;
  error: string;
  loading: boolean;
  onNavigate: (screen: NavigationScreen) => void;
  onClinicSelect: (clinic: Clinic) => void;
  onClinics: () => void;
  onLogout: () => void;
  run: <T>(t: () => Promise<T>, d: (v: T) => void) => void;
}) {
  const [data, setData] = useState(initial);
  const [editing, setEditing] = useState<TeamMember | null | undefined>(
    undefined,
  );
  const [temporary, setTemporary] = useState<{
    email: string;
    password: string;
  } | null>(null);
  async function refresh() {
    const result = await api<TeamResult>("/equipe");
    setData(result);
  }
  function changeActive(member: TeamMember) {
    const action = member.ativo ? "inativar" : "reativar";
    run(
      () => api(`/equipe/${member.id_usuario}/${action}`, { method: "POST" }),
      () => void refresh(),
    );
  }
  function resetPassword(member: TeamMember) {
    if (!window.confirm(`Gerar nova senha temporária para ${member.nome}?`))
      return;
    run(
      () =>
        api<{ senha_temporaria: string }>(
          `/equipe/${member.id_usuario}/redefinir-senha`,
          { method: "POST" },
        ),
      (result) => {
        setTemporary({
          email: member.email,
          password: result.senha_temporaria,
        });
        void refresh();
      },
    );
  }
  const limitReached = data.ativos >= data.limite;
  return (
    <main className="app-shell">
      <BusyOverlay visible={loading} message="Processando" />
      <AppSidebar current="team" identity={identity} clinic={clinic} clinics={clinics} onNavigate={onNavigate} onClinicSelect={onClinicSelect} onClinics={onClinics}/>
      <section className="workspace">
        <header className="topbar">
          <div className="topbar-context">
            <small>Administração</small>
            <strong>Equipe</strong>
          </div>
          <div className="topbar-user">
            <strong>{user?.email}</strong>
            <button className="logout-button" onClick={onLogout}>
              Sair
            </button>
          </div>
        </header>
        <main className="main-content">
          <div className="content">
            <div className="title-row">
              <div>
                <p className="eyebrow">ACESSOS DA ORGANIZAÇÃO</p>
                <h1>Equipe</h1>
                <p className="subtitle">
                  Crie até dois acessos vinculados, com perfil e clínicas
                  definidos.
                </p>
              </div>
              <button
                className="primary-button"
                disabled={limitReached}
                aria-describedby={limitReached ? "team-limit-notice" : undefined}
                onClick={() => setEditing(null)}
              >
                {limitReached ? "Limite atingido" : "+ Novo colaborador"}
              </button>
            </div>
            <div className="team-usage">
              <strong>
                {data.ativos}/{data.limite}
              </strong>
              <span>colaboradores ativos</span>
            </div>
            {limitReached && (
              <div id="team-limit-notice" className="team-limit-notice" role="status">
                <strong>Limite máximo de colaboradores atingido.</strong>
                <span>Inative um colaborador para liberar uma nova vaga.</span>
              </div>
            )}
            {error && (
              <div className="error-box" role="alert">
                {error}
              </div>
            )}
            <section className="team-list">
              {data.items.length === 0 ? (
                <div className="empty-state">
                  <strong>Nenhum colaborador cadastrado</strong>
                  <span>
                    A conta proprietária não consome uma das duas vagas.
                  </span>
                </div>
              ) : (
                data.items.map((member) => (
                  <article
                    className={`team-card${member.ativo ? "" : " inactive"}`}
                    key={member.id_usuario}
                  >
                    <div>
                      <strong>{member.nome}</strong>
                      <span>{member.email}</span>
                      <small>
                        {member.perfil_nome} • {member.clinic_ids.length}{" "}
                        clínica(s)
                        {member.troca_senha_obrigatoria
                          ? " • troca de senha pendente"
                          : ""}
                      </small>
                    </div>
                    <span
                      className={`status ${member.ativo ? "ok" : "danger"}`}
                    >
                      {member.ativo ? "ATIVO" : "INATIVO"}
                    </span>
                    <div className="team-actions">
                      <button onClick={() => setEditing(member)}>Editar</button>
                      <button
                        onClick={() => resetPassword(member)}
                        disabled={!member.ativo}
                      >
                        Redefinir senha
                      </button>
                      <button onClick={() => changeActive(member)}>
                        {member.ativo ? "Inativar" : "Reativar"}
                      </button>
                    </div>
                  </article>
                ))
              )}
            </section>
          </div>
        </main>
      </section>
      {editing !== undefined && (
        <TeamDialog
          member={editing}
          clinics={clinics}
          loading={loading}
          error={error}
          onClose={() => setEditing(undefined)}
          onSave={(payload) => {
            const path = editing ? `/equipe/${editing.id_usuario}` : "/equipe";
            run(
              () =>
                api<TeamMember & { senha_temporaria?: string }>(path, {
                  method: editing ? "PUT" : "POST",
                  body: JSON.stringify(payload),
                }),
              (result) => {
                setEditing(undefined);
                if (result.senha_temporaria)
                  setTemporary({
                    email: result.email,
                    password: result.senha_temporaria,
                  });
                void refresh();
              },
            );
          }}
        />
      )}
      {temporary && (
        <TemporaryPassword
          email={temporary.email}
          password={temporary.password}
          onClose={() => setTemporary(null)}
        />
      )}
    </main>
  );
}

function TeamDialog({
  member,
  clinics,
  loading,
  error,
  onClose,
  onSave,
}: {
  member: TeamMember | null;
  clinics: Clinic[];
  loading: boolean;
  error: string;
  onClose: () => void;
  onSave: (payload: {
    nome: string;
    email?: string;
    profile_code: string;
    clinic_ids: number[];
  }) => void;
}) {
  const [selected, setSelected] = useState<number[]>(member?.clinic_ids || []);
  return (
    <div className="modal-backdrop">
      <form
        className="modal team-dialog"
        onSubmit={(e) => {
          e.preventDefault();
          const d = new FormData(e.currentTarget);
          onSave({
            nome: String(d.get("nome")),
            ...(member ? {} : { email: String(d.get("email")) }),
            profile_code: String(d.get("profile_code")),
            clinic_ids: selected,
          });
        }}
      >
        <div className="modal-head">
          <div>
            <p className="eyebrow">ACESSO DE COLABORADOR</p>
            <h2>{member ? "Editar colaborador" : "Novo colaborador"}</h2>
          </div>
          <button type="button" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="form-grid">
          <label className="span-2">
            Nome completo
            <input name="nome" defaultValue={member?.nome || ""} required />
          </label>
          {!member && (
            <label className="span-2">
              E-mail
              <input name="email" type="email" required />
            </label>
          )}
          <label className="span-2">
            Perfil
            <select
              name="profile_code"
              defaultValue={member?.profile_code || "RECEPCAO"}
            >
              <option value="RECEPCAO">Recepção</option>
              <option value="FINANCEIRO">Financeiro</option>
            </select>
          </label>
          <fieldset className="span-2 clinic-checks">
            <legend>Clínicas permitidas</legend>
            {clinics.map((clinic) => (
              <label key={clinic.id_clinica}>
                <input
                  type="checkbox"
                  checked={selected.includes(clinic.id_clinica)}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, clinic.id_clinica]
                        : selected.filter((id) => id !== clinic.id_clinica),
                    )
                  }
                />
                {clinic.nome}
              </label>
            ))}
          </fieldset>
        </div>
        {selected.length === 0 && (
          <p className="required-note">Selecione pelo menos uma clínica.</p>
        )}
        {error && <div className="error-box">{error}</div>}
        <div className="modal-actions">
          <button type="button" className="ghost-button" onClick={onClose}>
            Cancelar
          </button>
          <button
            className="primary-button"
            disabled={loading || selected.length === 0}
          >
            {loading ? "Salvando…" : "Salvar acesso"}
          </button>
        </div>
      </form>
    </div>
  );
}

function TemporaryPassword({
  email,
  password,
  onClose,
}: {
  email: string;
  password: string;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop top">
      <section className="modal temporary-password">
        <p className="eyebrow">EXIBIÇÃO ÚNICA</p>
        <h2>Senha temporária criada</h2>
        <p>
          Compartilhe com segurança. O colaborador precisará trocá-la no
          primeiro acesso.
        </p>
        <label>
          E-mail
          <input readOnly value={email} />
        </label>
        <label>
          Senha temporária
          <input readOnly value={password} />
        </label>
        <div className="modal-actions">
          <button onClick={() => void navigator.clipboard.writeText(password)}>
            Copiar senha
          </button>
          <button className="primary-button" onClick={onClose}>
            Já guardei
          </button>
        </div>
      </section>
    </div>
  );
}

function Dashboard(props: {
  view: Exclude<NavigationScreen, "team" | "doctors" | "consultations">;
  user: User | null;
  identity: Identity | null;
  clinic: Clinic | null;
  clinics: Clinic[];
  patients: Patient[];
  patientResult: PatientResult;
  panel: ClinicPanel | null;
  activeFilter: ActiveFilter;
  patientPage: number;
  anamnesisStatus: AnamnesisStatus;
  search: string;
  setSearch: (s: string) => void;
  error: string;
  notice: string;
  loading: boolean;
  transitioning: boolean;
  onSearch: () => void;
  onActiveFilter: (value: ActiveFilter) => void;
  onPatientPage: (page: number) => void;
  onAnamnesisStatus: (status: AnamnesisStatus) => void;
  onClinic: () => void;
  onNavigate: (screen: NavigationScreen) => void;
  onClinicSelect: (clinic: Clinic) => void;
  onLogout: () => void;
  onNew: () => void;
  onCancelNew: () => void;
  newPatient: boolean;
  onPatientMode: (id: number) => void;
  onProfile: (id: number) => void;
  profile: Profile | null;
  history: HistoryItem[];
  onCloseProfile: () => void;
  onCreated: () => void;
  onDataChanged: () => void;
  run: <T>(t: () => Promise<T>, d: (v: T) => void) => void;
}) {
  const { clinic, patients } = props;
  const userInitials = props.user?.email?.slice(0, 2).toUpperCase() || "US";
  const pageCopy =
    props.view === "overview"
      ? { section: "Painel", title: "Visão geral", subtitle: "Acompanhe pacientes e anamneses da clínica atual." }
      : props.view === "anamneses"
        ? { section: "Prontuário digital", title: "Anamneses", subtitle: "Acompanhe o preenchimento e a revisão das anamneses." }
        : { section: "Prontuário digital", title: "Pacientes", subtitle: "Cadastros e anamneses da clínica em um só lugar." };
  useEffect(() => {
    document.body.dataset.canApprove = String(
      Boolean(props.identity?.permissoes.includes("ANAMNESIS_APPROVE")),
    );
  }, [props.identity]);
  return (
    <main className="app-shell">
      <BusyOverlay
        visible={props.loading || props.transitioning}
        message={props.transitioning ? "Abrindo tela" : "Carregando"}
      />
      <AppSidebar
        current={props.view}
        identity={props.identity}
        clinic={clinic}
        clinics={props.clinics}
        onNavigate={props.onNavigate}
        onClinicSelect={props.onClinicSelect}
        onClinics={props.onClinic}
      />
      <section className="workspace">
        <header className="topbar">
          <div className="topbar-context">
            <small>{pageCopy.title}</small>
            <strong>{clinic?.nome}</strong>
          </div>
          <div className="topbar-user">
            <div>
              <strong>{props.user?.email}</strong>
              <small>Conta autenticada</small>
            </div>
            <span className="topbar-avatar">{userInitials}</span>
            <button className="logout-button" onClick={props.onLogout}>
              Sair
            </button>
          </div>
        </header>
        <main className="main-content">
          <div className="content">
            <div className="title-row">
              <div>
                <p className="eyebrow">{pageCopy.section.toUpperCase()}</p>
                <h1>{pageCopy.title}</h1>
                <p className="subtitle">{pageCopy.subtitle}</p>
              </div>
              {props.view === "patients" && <button className="primary-button" onClick={props.onNew}>+ Novo paciente</button>}
            </div>
            {props.notice && (
              <div className="success-box" role="status">
                {props.notice}
              </div>
            )}
            {props.error && (
              <div className="error-box" role="alert">
                {props.error}
              </div>
            )}
            {props.view === "overview" && <OverviewPage panel={props.panel} clinic={clinic} canApprove={Boolean(props.identity?.permissoes.includes("ANAMNESIS_APPROVE"))} onNavigate={props.onNavigate} onNew={props.onNew} onProfile={props.onProfile} onFill={props.onPatientMode} />}
            {props.view === "patients" && <PatientsPage patients={patients} result={props.patientResult} search={props.search} setSearch={props.setSearch} activeFilter={props.activeFilter} loading={props.loading} onSearch={props.onSearch} onFilter={props.onActiveFilter} onPage={props.onPatientPage} onProfile={props.onProfile} onFill={props.onPatientMode} />}
            {props.view === "anamneses" && <AnamnesesPage patients={patients} result={props.patientResult} selected={props.anamnesisStatus} panel={props.panel} loading={props.loading} canApprove={Boolean(props.identity?.permissoes.includes("ANAMNESIS_APPROVE"))} onStatus={props.onAnamnesisStatus} onProfile={props.onProfile} onFill={props.onPatientMode} />}
          </div>
        </main>
        <footer className="footer">
          Billing Control • Gestão odontológica segura
        </footer>
      </section>
      {props.newPatient && (
        <PatientDialog
          clinic={clinic!}
          loading={props.loading}
          error={props.error}
          onClose={props.onCancelNew}
          onCreated={props.onCreated}
          run={props.run}
        />
      )}{" "}
      {props.profile && (
        <ProfileDialog
          profile={props.profile}
          history={props.history}
          canApprove={Boolean(props.identity?.permissoes.includes("ANAMNESIS_APPROVE"))}
          onChanged={props.onDataChanged}
          onClose={props.onCloseProfile}
        />
      )}
    </main>
  );
}

function PatientRows({ patients, loading, empty, canApprove = false, onProfile, onFill }: { patients: Patient[]; loading: boolean; empty: string; canApprove?: boolean; onProfile: (id: number) => void; onFill: (id: number) => void }) {
  if (!patients.length && !loading) return <div className="empty-state"><strong>{empty}</strong><span>Ajuste os filtros ou escolha outra situação.</span></div>;
  return <>{patients.map((patient) => (
    <article className="patient-row" key={patient.id_paciente}>
      <div className="patient-name"><span className="patient-avatar">{initials(patient.nome)}</span><div><strong>{patient.nome}</strong><small>{patient.telefone || "Sem telefone"}</small></div></div>
      <span>{patient.cpf_mascarado}</span>
      <span className={`status ${tone(patient.anamnese_status)}`}>{patient.anamnese_status || "PENDENTE"}</span>
      <div className="row-actions">
        <button onClick={() => onProfile(patient.id_paciente)}>{patient.anamnese_status === "PENDENTE_APROVACAO" && canApprove ? "Revisar" : "Perfil"}</button>
        {(patient.anamnese_status === "PENDENTE" || patient.anamnese_status === "VENCIDA" || patient.anamnese_status === "ATUALIZADA") && <button onClick={() => onFill(patient.id_paciente)}>{patient.anamnese_status === "VENCIDA" ? "Atualizar" : "Preencher"}</button>}
      </div>
    </article>
  ))}</>;
}

function OverviewPage({ panel, clinic, canApprove, onNavigate, onNew, onProfile, onFill }: { panel: ClinicPanel | null; clinic: Clinic | null; canApprove: boolean; onNavigate: (screen: NavigationScreen) => void; onNew: () => void; onProfile: (id: number) => void; onFill: (id: number) => void }) {
  const cards = [
    ["Pacientes ativos", panel?.pacientes_ativos ?? "—", "Na clínica"],
    ["Para preencher", panel?.pendentes_preenchimento ?? "—", "Sem anamnese"],
    ["Aguardando aprovação", panel?.pendentes_aprovacao ?? "—", "Revisão profissional"],
    ["Vencidas", panel?.vencidas ?? "—", "Precisam atualizar"],
    ["Atualizadas", panel?.atualizadas ?? "—", "Prontas para atendimento"],
  ];
  return <div className="overview-page">
    <section className="overview-hero"><div><span>Olá! Esta é a rotina de</span><strong>{clinic?.nome}</strong></div><div className="quick-actions"><button className="primary-button" onClick={onNew}>+ Novo paciente</button><button onClick={() => onNavigate("patients")}>Buscar paciente</button><button onClick={() => onNavigate("anamneses")}>Abrir fila</button></div></section>
    <div className="stats stats-five">{cards.map(([label, value, note]) => <article key={String(label)}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}</div>
    <section className="priorities"><div className="section-heading"><div><p className="eyebrow">ATENÇÃO</p><h2>Prioridades de hoje</h2></div><button className="link-button" onClick={() => onNavigate("anamneses")}>Ver toda a fila</button></div>
      {panel?.prioridades.length ? panel.prioridades.map((patient) => <article key={patient.id_paciente}><div className="patient-name"><span className="patient-avatar">{initials(patient.nome)}</span><div><strong>{patient.nome}</strong><small>{patient.cpf_mascarado}</small></div></div><span className={`status ${tone(patient.anamnese_status)}`}>{patient.anamnese_status}</span><button onClick={() => patient.anamnese_status === "PENDENTE_APROVACAO" ? onProfile(patient.id_paciente) : onFill(patient.id_paciente)}>{patient.anamnese_status === "PENDENTE_APROVACAO" ? (canApprove ? "Revisar e aprovar" : "Ver perfil") : patient.anamnese_status === "VENCIDA" ? "Atualizar" : "Preencher"}</button></article>) : <div className="empty-state compact"><strong>Nenhuma prioridade clínica</strong><span>A rotina está em dia.</span></div>}
    </section>
  </div>;
}

function PatientsPage({ patients, result, search, setSearch, activeFilter, loading, onSearch, onFilter, onPage, onProfile, onFill }: { patients: Patient[]; result: PatientResult; search: string; setSearch: (value: string) => void; activeFilter: ActiveFilter; loading: boolean; onSearch: () => void; onFilter: (value: ActiveFilter) => void; onPage: (page: number) => void; onProfile: (id: number) => void; onFill: (id: number) => void }) {
  const pages = Math.max(1, Math.ceil(result.total / result.page_size));
  return <section className="patient-panel directory-panel"><div className="directory-tools"><form className="panel-toolbar" onSubmit={(event) => { event.preventDefault(); onSearch(); }}><label><span className="sr-only">Buscar</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar por nome, CPF ou telefone" /></label><button className="filter-button">Buscar</button></form><div className="segmented" aria-label="Filtrar pacientes">{([['true','Ativos'],['false','Inativos'],['all','Todos']] as [ActiveFilter,string][]).map(([value,label]) => <button key={value} className={activeFilter === value ? "active" : ""} onClick={() => onFilter(value)}>{label}</button>)}</div></div><div className="directory-summary"><strong>{result.total}</strong> paciente(s) encontrado(s)<span>Página {result.page} de {pages}</span></div><div className="table-head"><span>Paciente</span><span>CPF</span><span>Anamnese</span><span>Ações</span></div><PatientRows patients={patients} loading={loading} empty="Nenhum paciente encontrado" onProfile={onProfile} onFill={onFill} /><div className="pagination"><button disabled={result.page <= 1} onClick={() => onPage(result.page - 1)}>← Anterior</button><span>Página {result.page} de {pages}</span><button disabled={result.page >= pages} onClick={() => onPage(result.page + 1)}>Próxima →</button></div></section>;
}

function AnamnesesPage({ patients, result, selected, panel, loading, canApprove, onStatus, onProfile, onFill }: { patients: Patient[]; result: PatientResult; selected: AnamnesisStatus; panel: ClinicPanel | null; loading: boolean; canApprove: boolean; onStatus: (status: AnamnesisStatus) => void; onProfile: (id: number) => void; onFill: (id: number) => void }) {
  const tabs: [AnamnesisStatus,string,number][] = [["PENDENTE","Para preencher",panel?.pendentes_preenchimento || 0],["PENDENTE_APROVACAO","Aguardando aprovação",panel?.pendentes_aprovacao || 0],["VENCIDA","Vencidas",panel?.vencidas || 0],["ATUALIZADA","Atualizadas",panel?.atualizadas || 0]];
  return <section className="anamnesis-board"><div className="anamnesis-tabs" role="tablist">{tabs.map(([value,label,count]) => <button role="tab" aria-selected={selected === value} className={selected === value ? "active" : ""} key={value} onClick={() => onStatus(value)}><span>{label}</span><strong>{count}</strong></button>)}</div><div className="queue-heading"><div><p className="eyebrow">FILA SELECIONADA</p><h2>{tabs.find(([value]) => value === selected)?.[1]}</h2></div><span>{result.total} registro(s)</span></div><div className="table-head"><span>Paciente</span><span>CPF</span><span>Situação</span><span>Ação adequada</span></div><PatientRows patients={patients} loading={loading} empty="Nenhuma anamnese nesta fila" canApprove={canApprove} onProfile={onProfile} onFill={onFill} /></section>;
}

function ProfileDialog({
  profile,
  history,
  canApprove,
  onChanged,
  onClose,
}: {
  profile: Profile;
  history: HistoryItem[];
  canApprove: boolean;
  onChanged: () => void;
  onClose: () => void;
}) {
  const [items, setItems] = useState(history);
  const [approvalError, setApprovalError] = useState("");
  const [remoteLink, setRemoteLink] = useState<RemoteLink | null>(null);
  async function generateLink() {
    try {
      setRemoteLink(
        await api<RemoteLink>(
          `/clinicas/${profile.id_clinica}/anamnese/links`,
          {
            method: "POST",
            body: JSON.stringify({
              patient_id: profile.id_paciente,
              canal_compartilhamento: "COPY",
            }),
          },
        ),
      );
      setApprovalError("");
    } catch (err) {
      setApprovalError(
        err instanceof Error ? err.message : "Não foi possível gerar o link",
      );
    }
  }
  async function share() {
    if (!remoteLink) return;
    const data = {
      title: "Anamnese odontológica",
      text: "Acesse o link seguro para preencher sua anamnese:",
      url: remoteLink.url,
    };
    if (navigator.share) await navigator.share(data);
    else await navigator.clipboard.writeText(remoteLink.url);
  }
  async function approve(v: HistoryItem) {
    const nome = window
      .prompt("Nome completo do profissional responsável:")
      ?.trim();
    if (!nome) return;
    const cro = window.prompt("CRO do profissional responsável:")?.trim();
    if (!cro) return;
    if (
      !window.confirm(
        "Confirmo que revisei esta anamnese e assumo responsabilidade clínica por sua aprovação.",
      )
    )
      return;
    try {
      await api(
        `/clinicas/${profile.id_clinica}/pacientes/${profile.id_paciente}/anamnese/${v.id_anamnese_versao}/aprovar`,
        {
          method: "POST",
          body: JSON.stringify({
            nome_profissional: nome,
            cro_profissional: cro,
            declaracao_confirmada: true,
          }),
        },
      );
      setItems(
        items.map((item) =>
          item.id_anamnese_versao === v.id_anamnese_versao
            ? {
                ...item,
                status_aprovacao: "APROVADA",
                nome_profissional: nome,
                cro_profissional: cro,
                aprovado_em: new Date().toISOString(),
              }
            : item,
        ),
      );
      setApprovalError("");
      onChanged();
    } catch (err) {
      setApprovalError(
        err instanceof Error
          ? err.message
          : "Não foi possível aprovar a anamnese",
      );
    }
  }
  return (
    <div className="modal-backdrop">
      <section className="modal profile-modal">
        <div className="modal-head">
          <div>
            <p className="eyebrow">PERFIL DO PACIENTE</p>
            <h2>{profile.nome}</h2>
          </div>
          <button onClick={onClose}>×</button>
        </div>
        <div className="profile-status">
          <span className={`status ${tone(profile.anamnese_status)}`}>
            {profile.anamnese_status}
          </span>
          <span>{profile.telefone || "Sem telefone"}</span>
          <span>{profile.email || "Sem e-mail"}</span>
        </div>
        <section className="remote-link-panel">
          <h3>Preenchimento remoto</h3>
          <p>
            Gere um link protegido por CPF e data de nascimento, válido por 24
            horas.
          </p>
          {remoteLink ? (
            <>
              <input readOnly value={remoteLink.url} />
              <small>
                Expira em{" "}
                {new Date(remoteLink.expires_at).toLocaleString("pt-BR")}
              </small>
              <div className="remote-actions">
                <button onClick={() => void share()}>Compartilhar</button>
                <a
                  href={`https://wa.me/?text=${encodeURIComponent(`Preencha sua anamnese: ${remoteLink.url}`)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  WhatsApp
                </a>
                <a
                  href={`mailto:?subject=Anamnese odontológica&body=${encodeURIComponent(remoteLink.url)}`}
                >
                  E-mail
                </a>
                <button
                  onClick={() =>
                    void navigator.clipboard.writeText(remoteLink.url)
                  }
                >
                  Copiar
                </button>
              </div>
            </>
          ) : (
            <button
              className="primary-button"
              onClick={() => void generateLink()}
            >
              Gerar link de anamnese
            </button>
          )}
        </section>
        {profile.alerts && profile.alerts.length > 0 && (
          <section className="alerts">
            <h3>Alertas clínicos</h3>
            {profile.alerts.map((a) => (
              <strong key={a.codigo}>{a.descricao}</strong>
            ))}
          </section>
        )}
        <div className="profile-columns">
          <section>
            <h3>Dados pessoais</h3>
            <dl>
              <dt>Data de nascimento</dt>
              <dd>{profile.data_nascimento}</dd>
              <dt>Plano</dt>
              <dd>{profile.plano_odontologico || "Não informado"}</dd>
              <dt>Endereço</dt>
              <dd>{profile.endereco || "Não informado"}</dd>
            </dl>
          </section>
          <section>
            <h3>Histórico de anamnese</h3>
            {items.length ? (
              items.map((v) => (
                <article className="history-item" key={v.id_anamnese_versao}>
                  <div>
                    <strong>Versão {v.numero_versao}</strong>
                    <small>
                      {v.status_aprovacao === "APROVADA"
                        ? `Aprovada por ${v.nome_profissional} • ${v.cro_profissional}`
                        : "Aguardando aprovação profissional"}
                    </small>
                  </div>
                  <span>
                    {new Date(v.aceito_em).toLocaleDateString("pt-BR")}
                  </span>
                  {v.status_aprovacao !== "APROVADA" && canApprove && (
                    <button
                      className="link-button"
                      onClick={() => void approve(v)}
                    >
                      Revisar e aprovar
                    </button>
                  )}
                </article>
              ))
            ) : (
              <p className="subtitle">Nenhuma versão registrada.</p>
            )}
          </section>
        </div>
        {approvalError && (
          <div className="error-box" role="alert">
            {approvalError}
          </div>
        )}
        <div className="modal-actions">
          <button className="primary-button" onClick={onClose}>
            Fechar
          </button>
        </div>
      </section>
    </div>
  );
}
function PatientDialog({
  clinic,
  loading,
  error,
  onClose,
  onCreated,
  run,
}: {
  clinic: Clinic;
  loading: boolean;
  error: string;
  onClose: () => void;
  onCreated: () => void;
  run: <T>(t: () => Promise<T>, d: (v: T) => void) => void;
}) {
  const [birth, setBirth] = useState("");
  const minor = useMemo(
    () =>
      birth
        ? new Date().getFullYear() -
            new Date(`${birth}T12:00:00`).getFullYear() <
          18
        : false,
    [birth],
  );
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (loading) return;
    const data = new FormData(e.currentTarget);
    const text = (key: string) => String(data.get(key) || "") || null;
    const payload: PatientPayload = {
      nome: data.get("nome"),
      cpf: data.get("cpf"),
      data_nascimento: birth,
      sexo: data.get("sexo"),
      telefone: text("telefone"),
      email: text("email"),
      endereco: text("endereco"),
      plano_odontologico: text("plano"),
      idempotency_key: crypto.randomUUID(),
    };
    if (minor)
      payload.responsavel = {
        nome: data.get("rnome"),
        cpf: data.get("rcpf"),
        telefone: data.get("rtelefone"),
        email: text("remail"),
        parentesco: data.get("parentesco"),
      };
    run(
      () =>
        api(`/clinicas/${clinic.id_clinica}/pacientes`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      onCreated,
    );
  }
  return (
    <div className="modal-backdrop">
      <form className="modal" onSubmit={submit}>
        <div className="modal-head">
          <div>
            <p className="eyebrow">NOVO CADASTRO</p>
            <h2>Novo paciente</h2>
          </div>
          <button type="button" onClick={onClose} disabled={loading}>
            ×
          </button>
        </div>
        <p className="required-note">
          <span>*</span> Campos obrigatórios
        </p>
        <div className="form-grid">
          <label className="span-2">
            Nome completo
            <input name="nome" required />
          </label>
          <label>
            CPF
            <input name="cpf" required inputMode="numeric" />
          </label>
          <label>
            Data de nascimento
            <input
              type="date"
              value={birth}
              onChange={(e) => setBirth(e.target.value)}
              required
            />
          </label>
          <label>
            Sexo
            <select name="sexo">
              <option value="NAO_INFORMADO">Não informado</option>
              <option>FEMININO</option>
              <option>MASCULINO</option>
              <option>OUTRO</option>
            </select>
          </label>
          <label>
            Telefone
            <input name="telefone" />
          </label>
          <label>
            E-mail
            <input name="email" type="email" />
          </label>
          <label>
            Plano odontológico
            <input name="plano" />
          </label>
          <label className="span-2">
            Endereço
            <input name="endereco" />
          </label>
          {minor && (
            <>
              <h3 className="span-2">Responsável legal</h3>
              <label className="span-2">
                Nome
                <input name="rnome" required />
              </label>
              <label>
                CPF
                <input name="rcpf" required />
              </label>
              <label>
                Telefone
                <input name="rtelefone" required />
              </label>
              <label>
                E-mail
                <input name="remail" type="email" />
              </label>
              <label>
                Parentesco
                <input name="parentesco" required />
              </label>
            </>
          )}
        </div>
        {error && (
          <div className="error-box" role="alert">
            {error}
          </div>
        )}
        <div className="modal-actions">
          <button
            type="button"
            className="ghost-button"
            onClick={onClose}
            disabled={loading}
          >
            Cancelar
          </button>
          <button className="primary-button" disabled={loading}>
            {loading ? "Cadastrando…" : "Cadastrar paciente"}
          </button>
        </div>
      </form>
    </div>
  );
}
function PatientMode({
  form,
  error,
  loading,
  onSubmit,
  onCancel,
}: {
  form: FormDefinition;
  error: string;
  loading: boolean;
  onSubmit: (p: unknown) => void;
  onCancel: () => void;
}) {
  const [answers, setAnswers] = useState<Record<number, string | boolean>>({});
  function visible(q: Question) {
    return (
      !q.parent_question_id ||
      String(answers[q.parent_question_id]) === q.show_when_value
    );
  }
  return (
    <main className="patient-mode">
      <header>
        <div className="brand dark">
          <span className="brand-mark">B</span>
          <span>Billing Control</span>
        </div>
        <span>Modo paciente • sessão protegida</span>
      </header>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const data = new FormData(e.currentTarget);
          onSubmit({
            answers: Object.entries(answers).map(([question_id, value]) => ({
              question_id: Number(question_id),
              value,
            })),
            acceptance: {
              nome: data.get("accept_name"),
              cpf: data.get("accept_cpf"),
              termos_aceitos: true,
            },
            idempotency_key: crypto.randomUUID(),
          });
        }}
      >
        {form.modo_teste && (
          <div className="test-form-banner" role="alert">
            <strong>Formulário de teste — sem validade clínica</strong>
            <span>Uso exclusivo no ambiente controlado de validação.</span>
          </div>
        )}
        <p className="eyebrow">ANAMNESE • VERSÃO {form.versao}</p>
        <h1>{form.nome}</h1>
        <p className="subtitle">
          Responda com atenção. Essas informações ajudam a tornar seu
          atendimento mais seguro.
        </p>
        <div className="question-list">
          {form.questions.filter(visible).map((q) => (
            <fieldset key={q.id_pergunta}>
              <legend>
                {q.texto}
                {q.obrigatoria && <sup>*</sup>}
              </legend>
              {q.tipo === "BOOLEAN" ? (
                <div className="choice-row">
                  <label>
                    <input
                      type="radio"
                      name={`q${q.id_pergunta}`}
                      required={q.obrigatoria}
                      onChange={() =>
                        setAnswers({ ...answers, [q.id_pergunta]: true })
                      }
                    />{" "}
                    Sim
                  </label>
                  <label>
                    <input
                      type="radio"
                      name={`q${q.id_pergunta}`}
                      onChange={() =>
                        setAnswers({ ...answers, [q.id_pergunta]: false })
                      }
                    />{" "}
                    Não
                  </label>
                </div>
              ) : (
                <input
                  required={q.obrigatoria}
                  onChange={(e) =>
                    setAnswers({ ...answers, [q.id_pergunta]: e.target.value })
                  }
                />
              )}
            </fieldset>
          ))}
        </div>
        <section className="acceptance">
          <h2>Confirmação e aceite</h2>
          <p>{form.termos_texto}</p>
          <div className="form-grid">
            <label>
              Nome de quem confirma
              <input name="accept_name" required />
            </label>
            <label>
              CPF
              <input name="accept_cpf" required />
            </label>
          </div>
          <label className="check">
            <input type="checkbox" required /> Li e confirmo as informações e os
            termos acima.
          </label>
        </section>
        {error && <div className="error-box">{error}</div>}
        <div className="mode-actions">
          <button type="button" className="ghost-button" onClick={onCancel}>
            Cancelar
          </button>
          <button className="primary-button" disabled={loading}>
            Concluir anamnese
          </button>
        </div>
      </form>
    </main>
  );
}
function Locked({
  outcome,
  onUnlock,
}: {
  outcome: "completed" | "cancelled";
  onUnlock: () => void;
}) {
  const completed = outcome === "completed";
  return (
    <main className="locked">
      <div>
        <span className={`lock-icon${completed ? "" : " cancelled"}`}>
          {completed ? "✓" : "×"}
        </span>
        <h1>
          {completed
            ? "Anamnese enviada para revisão"
            : "Preenchimento cancelado"}
        </h1>
        <p>
          {completed
            ? "As respostas e o aceite foram registrados. A anamnese aguarda revisão do profissional responsável. Entregue o dispositivo à recepção."
            : "Nenhuma resposta foi enviada. Entregue o dispositivo à recepção."}
        </p>
        <button className="primary-button" onClick={onUnlock}>
          Bloquear e voltar ao login
        </button>
      </div>
    </main>
  );
}
function RemoteAnamnesis({ token }: { token: string }) {
  const [verified, setVerified] = useState(false);
  const [form, setForm] = useState<FormDefinition | null>(null);
  const [error, setError] = useState(
    token ? "" : "Link inválido ou incompleto.",
  );
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [role, setRole] = useState("PACIENTE");
  async function verify(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const d = new FormData(e.currentTarget);
    try {
      const result = await api<{ papel_confirmante: string }>(
        "/modo-paciente/verificar",
        {
          method: "POST",
          body: JSON.stringify({
            cpf: d.get("cpf"),
            data_nascimento: d.get("birth"),
          }),
        },
        token,
      );
      setRole(result.papel_confirmante);
      setForm(
        await api<FormDefinition>("/modo-paciente/formulario", {}, token),
      );
      setVerified(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Não foi possível confirmar sua identidade",
      );
    } finally {
      setLoading(false);
    }
  }
  if (done)
    return (
      <main className="locked">
        <div>
          <span className="lock-icon">✓</span>
          <h1>Anamnese enviada para revisão</h1>
          <p>
            As respostas foram recebidas com segurança e serão revisadas pelo
            profissional responsável. Este link não pode ser reutilizado.
          </p>
        </div>
      </main>
    );
  if (!verified || !form)
    return (
      <main className="remote-identity">
        <form onSubmit={verify}>
          <div className="brand dark">
            <span className="brand-mark">B</span>
            <span>Billing Control</span>
          </div>
          <p className="eyebrow">LINK SEGURO DE ANAMNESE</p>
          <h1>Confirme sua identidade</h1>
          <p className="subtitle">
            Nenhuma informação de saúde será exibida antes da confirmação.
          </p>
          <label>
            CPF {role === "RESPONSAVEL" ? "do responsável" : ""}
            <input name="cpf" inputMode="numeric" required />
          </label>
          <label>
            Data de nascimento do paciente
            <input name="birth" type="date" required />
          </label>
          {error && (
            <div className="error-box" role="alert">
              {error}
            </div>
          )}
          <button className="primary-button wide" disabled={loading || !token}>
            {loading ? "Confirmando…" : "Continuar"}
          </button>
          <small>
            Seus dados serão usados somente para confirmar o acesso. O link
            expira e funciona uma única vez.
          </small>
        </form>
      </main>
    );
  return (
    <PatientMode
      form={form}
      error={error}
      loading={loading}
      onCancel={() => {
        setError("O link continua disponível até expirar ou ser revogado.");
        setVerified(false);
        setForm(null);
      }}
      onSubmit={async (payload) => {
        setLoading(true);
        setError("");
        try {
          await api(
            "/modo-paciente/anamnese",
            { method: "POST", body: JSON.stringify(payload) },
            token,
          );
          setDone(true);
        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : "Não foi possível enviar a anamnese",
          );
        } finally {
          setLoading(false);
        }
      }}
    />
  );
}
function ConsultasPage({
  user,
  identity,
  clinic,
  clinics,
  result,
  search,
  setSearch,
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
  doctorId,
  page,
  detail,
  error,
  loading,
  onNavigate,
  onClinicSelect,
  onClinics,
  onLogout,
  onSearch,
  onDoctorFilter,
  onPage,
  onDetail,
  onCloseDetail,
}: {
  user: User | null;
  identity: Identity | null;
  clinic: Clinic | null;
  clinics: Clinic[];
  result: ConsultationResult;
  search: string;
  setSearch: (s: string) => void;
  dateFrom: string;
  setDateFrom: (s: string) => void;
  dateTo: string;
  setDateTo: (s: string) => void;
  doctorId: number | null;
  page: number;
  detail: ConsultationDetail | null;
  error: string;
  loading: boolean;
  onNavigate: (screen: NavigationScreen) => void;
  onClinicSelect: (clinic: Clinic) => void;
  onClinics: () => void;
  onLogout: () => void;
  onSearch: () => void;
  onDoctorFilter: (id: number | null) => void;
  onPage: (page: number) => void;
  onDetail: (id: number) => void;
  onCloseDetail: () => void;
}) {
  const pages = Math.max(1, Math.ceil(result.total / result.page_size));
  const fmtCurrency = (v: number | null) =>
    v == null ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const fmtDate = (s: string | null) =>
    s ? new Date(s + "T00:00:00").toLocaleDateString("pt-BR") : "—";
  return (
    <main className="app-shell">
      <BusyOverlay visible={loading} message="Carregando" />
      <AppSidebar current="consultations" identity={identity} clinic={clinic} clinics={clinics} onNavigate={onNavigate} onClinicSelect={onClinicSelect} onClinics={onClinics} />
      <section className="workspace">
        <header className="topbar">
          <div className="topbar-context">
            <small>Atendimentos</small>
            <strong>{clinic?.nome}</strong>
          </div>
          <div className="topbar-user">
            <strong>{user?.email}</strong>
            <button className="logout-button" onClick={onLogout}>Sair</button>
          </div>
        </header>
        <main className="main-content">
          <div className="content">
            <div className="title-row">
              <div>
                <p className="eyebrow">ATENDIMENTOS</p>
                <h1>Consultas</h1>
                <p className="subtitle">Histórico de atendimentos desta clínica — somente leitura.</p>
              </div>
            </div>
            {error && <div className="error-box" role="alert">{error}</div>}
            <div className="directory-tools">
              <form className="panel-toolbar" onSubmit={(e) => { e.preventDefault(); onSearch(); }}>
                <label>
                  <span className="sr-only">Buscar paciente</span>
                  <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar por paciente" />
                </label>
                <label>
                  <span className="sr-only">De</span>
                  <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} title="Data início" />
                </label>
                <label>
                  <span className="sr-only">Até</span>
                  <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} title="Data fim" />
                </label>
                <button className="filter-button">Buscar</button>
              </form>
            </div>
            <div className="directory-summary">
              <strong>{result.total}</strong> consulta(s) encontrada(s)
              <span>Página {result.page} de {pages}</span>
            </div>
            <div className="table-head" style={{ gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr 1fr 1fr" }}>
              <span>Paciente</span>
              <span>Doutor</span>
              <span>Data</span>
              <span>Status</span>
              <span>Valor</span>
              <span>Qualidade</span>
              <span>Ação</span>
            </div>
            {result.items.length === 0 && !loading ? (
              <div className="empty-state">
                <strong>Nenhuma consulta encontrada</strong>
                <span>Ajuste os filtros ou verifique o período selecionado.</span>
              </div>
            ) : (
              result.items.map((c) => (
                <article className={`patient-row${c.divergencia_valor ? " warn" : ""}`} key={c.id_consulta}>
                  <div className="patient-name">
                    <span className="patient-avatar">{initials(c.nome_paciente || "?")}</span>
                    <div>
                      <strong>{c.nome_paciente || "Paciente não localizado"}</strong>
                      {!c.flag_paciente_localizado && <small className="tag danger">Sem vínculo</small>}
                    </div>
                  </div>
                  <span>{c.nome_doutor || "—"}</span>
                  <span>{fmtDate(c.data_consulta)}</span>
                  <span className="status ok">{c.status || "—"}</span>
                  <div>
                    <span>{fmtCurrency(c.valor_total)}</span>
                    {c.divergencia_valor && <small className="tag warn">Divergência</small>}
                  </div>
                  <span>{c.total_itens} item(s)</span>
                  <div className="row-actions">
                    <button onClick={() => onDetail(c.id_consulta)}>Ver</button>
                  </div>
                </article>
              ))
            )}
            <div className="pagination">
              <button disabled={result.page <= 1} onClick={() => onPage(result.page - 1)}>← Anterior</button>
              <span>Página {result.page} de {pages}</span>
              <button disabled={result.page >= pages} onClick={() => onPage(result.page + 1)}>Próxima →</button>
            </div>
          </div>
        </main>
        <footer className="footer">Billing Control • Gestão odontológica segura</footer>
      </section>
      {detail && (
        <div className="modal-backdrop">
          <section className="modal profile-modal">
            <div className="modal-head">
              <div>
                <p className="eyebrow">CONSULTA #{detail.id_consulta}</p>
                <h2>{detail.nome_paciente || detail.nome_paciente_origem || "Paciente não localizado"}</h2>
              </div>
              <button onClick={onCloseDetail}>×</button>
            </div>
            <div className="profile-status">
              <span className="status ok">{detail.status}</span>
              {detail.divergencia_valor && <span className="tag warn">Divergência de valores</span>}
              {!detail.flag_paciente_localizado && <span className="tag danger">Paciente sem vínculo</span>}
            </div>
            <div className="profile-columns">
              <section>
                <h3>Atendimento</h3>
                <dl>
                  <dt>Data</dt>
                  <dd>{fmtDate(detail.data_consulta)}</dd>
                  <dt>Doutor</dt>
                  <dd>{detail.nome_doutor || "—"}{detail.especialidade ? ` — ${detail.especialidade}` : ""}</dd>
                  <dt>Valor cabeçalho</dt>
                  <dd>{fmtCurrency(detail.valor_total)}</dd>
                  <dt>Soma dos itens</dt>
                  <dd className={detail.divergencia_valor ? "warn-text" : ""}>{fmtCurrency(detail.soma_itens)}</dd>
                </dl>
              </section>
              <section>
                <h3>Qualidade de vínculo</h3>
                <dl>
                  <dt>Paciente localizado</dt>
                  <dd>{detail.flag_paciente_localizado ? "Sim" : "Não"}</dd>
                  {detail.tipo_match_paciente && <><dt>Tipo de match</dt><dd>{detail.tipo_match_paciente}</dd></>}
                  {detail.nome_paciente_origem && <><dt>Nome de origem</dt><dd>{detail.nome_paciente_origem}</dd></>}
                </dl>
              </section>
            </div>
            {detail.itens.length > 0 && (
              <section style={{ marginTop: "1rem" }}>
                <h3>Procedimentos ({detail.itens.length})</h3>
                <div className="table-head" style={{ gridTemplateColumns: "2fr 1fr 2fr 1fr" }}>
                  <span>Procedimento</span>
                  <span>Dente</span>
                  <span>Descrição</span>
                  <span>Valor</span>
                </div>
                {detail.itens.map((item) => (
                  <div className="patient-row" key={item.id_consulta_procedimento} style={{ gridTemplateColumns: "2fr 1fr 2fr 1fr" }}>
                    <span>{item.nome_procedimento || "—"}</span>
                    <span>{item.elemento_dental || "—"}</span>
                    <span>{item.descricao || "—"}</span>
                    <span>{fmtCurrency(item.valor_consulta)}</span>
                  </div>
                ))}
              </section>
            )}
            <div className="modal-actions">
              <button className="primary-button" onClick={onCloseDetail}>Fechar</button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
function DoctorsPage({
  user,
  identity,
  clinic,
  clinics,
  result,
  search,
  setSearch,
  activeFilter,
  page,
  detail,
  error,
  loading,
  onNavigate,
  onClinicSelect,
  onClinics,
  onLogout,
  onSearch,
  onActiveFilter,
  onPage,
  onDetail,
  onCloseDetail,
}: {
  user: User | null;
  identity: Identity | null;
  clinic: Clinic | null;
  clinics: Clinic[];
  result: DoctorResult;
  search: string;
  setSearch: (s: string) => void;
  activeFilter: ActiveFilter;
  page: number;
  detail: DoctorDetail | null;
  error: string;
  loading: boolean;
  onNavigate: (screen: NavigationScreen) => void;
  onClinicSelect: (clinic: Clinic) => void;
  onClinics: () => void;
  onLogout: () => void;
  onSearch: () => void;
  onActiveFilter: (value: ActiveFilter) => void;
  onPage: (page: number) => void;
  onDetail: (id: number) => void;
  onCloseDetail: () => void;
}) {
  const pages = Math.max(1, Math.ceil(result.total / result.page_size));
  return (
    <main className="app-shell">
      <BusyOverlay visible={loading} message="Carregando" />
      <AppSidebar current="doctors" identity={identity} clinic={clinic} clinics={clinics} onNavigate={onNavigate} onClinicSelect={onClinicSelect} onClinics={onClinics} />
      <section className="workspace">
        <header className="topbar">
          <div className="topbar-context">
            <small>Corpo clínico</small>
            <strong>{clinic?.nome}</strong>
          </div>
          <div className="topbar-user">
            <strong>{user?.email}</strong>
            <button className="logout-button" onClick={onLogout}>Sair</button>
          </div>
        </header>
        <main className="main-content">
          <div className="content">
            <div className="title-row">
              <div>
                <p className="eyebrow">CORPO CLÍNICO</p>
                <h1>Doutores</h1>
                <p className="subtitle">Profissionais vinculados a esta clínica.</p>
              </div>
            </div>
            {error && <div className="error-box" role="alert">{error}</div>}
            <div className="directory-tools">
              <form className="panel-toolbar" onSubmit={(e) => { e.preventDefault(); onSearch(); }}>
                <label>
                  <span className="sr-only">Buscar</span>
                  <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar por nome" />
                </label>
                <button className="filter-button">Buscar</button>
              </form>
              <div className="segmented" aria-label="Filtrar doutores">
                {([["all", "Todos"], ["true", "Ativos"], ["false", "Inativos"]] as [ActiveFilter, string][]).map(([value, label]) => (
                  <button key={value} className={activeFilter === value ? "active" : ""} onClick={() => onActiveFilter(value)}>{label}</button>
                ))}
              </div>
            </div>
            <div className="directory-summary">
              <strong>{result.total}</strong> doutor(es) encontrado(s)
              <span>Página {result.page} de {pages}</span>
            </div>
            <div className="table-head">
              <span>Doutor</span>
              <span>Especialidade</span>
              <span>CRO</span>
              <span>Consultas</span>
              <span>Situação</span>
              <span>Ação</span>
            </div>
            {result.items.length === 0 && !loading ? (
              <div className="empty-state">
                <strong>Nenhum doutor encontrado</strong>
                <span>Ajuste os filtros ou verifique os vínculos da clínica.</span>
              </div>
            ) : (
              result.items.map((doctor) => (
                <article className={`patient-row${doctor.flag_ativo ? "" : " inactive"}`} key={doctor.id_doutor}>
                  <div className="patient-name">
                    <span className="patient-avatar">{initials(doctor.nome_doutor)}</span>
                    <div>
                      <strong>{doctor.nome_doutor}</strong>
                      <small>{doctor.percentual_repasse != null ? `${doctor.percentual_repasse}% repasse` : "Sem repasse definido"}</small>
                    </div>
                  </div>
                  <span>{doctor.especialidade || "—"}</span>
                  <span>{doctor.cro ? `${doctor.cro_estado || ""} ${doctor.cro}`.trim() : "—"}</span>
                  <span>{doctor.total_consultas}</span>
                  <span className={`status ${doctor.flag_ativo ? "ok" : "danger"}`}>{doctor.flag_ativo ? "ATIVO" : "INATIVO"}</span>
                  <div className="row-actions">
                    <button onClick={() => onDetail(doctor.id_doutor)}>Ver detalhes</button>
                  </div>
                </article>
              ))
            )}
            <div className="pagination">
              <button disabled={result.page <= 1} onClick={() => onPage(result.page - 1)}>← Anterior</button>
              <span>Página {result.page} de {pages}</span>
              <button disabled={result.page >= pages} onClick={() => onPage(result.page + 1)}>Próxima →</button>
            </div>
          </div>
        </main>
        <footer className="footer">Billing Control • Gestão odontológica segura</footer>
      </section>
      {detail && (
        <div className="modal-backdrop">
          <section className="modal profile-modal">
            <div className="modal-head">
              <div>
                <p className="eyebrow">DOUTOR</p>
                <h2>{detail.nome_doutor}</h2>
              </div>
              <button onClick={onCloseDetail}>×</button>
            </div>
            <div className="profile-status">
              <span className={`status ${detail.flag_ativo ? "ok" : "danger"}`}>{detail.flag_ativo ? "ATIVO" : "INATIVO"}</span>
              {detail.especialidade && <span>{detail.especialidade}</span>}
              {detail.cro && <span>CRO {detail.cro_estado || ""} {detail.cro}</span>}
            </div>
            <div className="profile-columns">
              <section>
                <h3>Dados profissionais</h3>
                <dl>
                  <dt>Especialidade</dt>
                  <dd>{detail.especialidade || "Não informada"}</dd>
                  <dt>CRO</dt>
                  <dd>{detail.cro ? `${detail.cro_estado || ""} ${detail.cro}`.trim() : "Não informado"}</dd>
                  <dt>Repasse</dt>
                  <dd>{detail.percentual_repasse != null ? `${detail.percentual_repasse}%` : "Não definido"}</dd>
                </dl>
              </section>
              <section>
                <h3>Vínculo com a clínica</h3>
                <dl>
                  <dt>Início</dt>
                  <dd>{detail.data_inicio ? new Date(detail.data_inicio).toLocaleDateString("pt-BR") : "Não informado"}</dd>
                  <dt>Término</dt>
                  <dd>{detail.data_fim ? new Date(detail.data_fim).toLocaleDateString("pt-BR") : "Em aberto"}</dd>
                  <dt>Consultas realizadas</dt>
                  <dd>{detail.total_consultas}</dd>
                </dl>
              </section>
            </div>
            <div className="modal-actions">
              <button className="primary-button" onClick={onCloseDetail}>Fechar</button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

function Loading() {
  return (
    <main className="loading-page">
      <span></span>
      <p>Carregando Billing Control…</p>
    </main>
  );
}
function BusyOverlay({ visible, message }: { visible: boolean; message: string }) {
  if (!visible) return null;
  return (
    <div className="busy-overlay" role="status" aria-live="polite" aria-label={`${message}...`}>
      <div className="busy-pill">
        <span>{message}</span>
        <span className="busy-dots" aria-hidden="true"><i></i><i></i><i></i></span>
      </div>
    </div>
  );
}
function initials(name: string) {
  return name
    .split(" ")
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();
}
function tone(status?: string) {
  return status === "ATUALIZADA"
    ? "ok"
    : status === "VENCIDA"
      ? "danger"
      : "warn";
}
