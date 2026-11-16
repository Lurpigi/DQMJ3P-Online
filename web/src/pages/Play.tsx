import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, apiUrl, createAzaharAccount, useApi } from "../api";
import {
  applyIdentity, friendCode, newSecret, playerPassword, readIdentity, readIps, VARIANTS, writeIps,
  type Identity, type IpsRecord, type Variant,
} from "../azahar";

const MODS_PATH = "<Azahar user folder>/load/mods/00040000001ACB00/exefs/code.ips";
type Mark = "yes" | "no";
// Rows: what each kind of account can do (README.md "Accounts" has the same table)
const FEATURES: [string, Mark, Mark, Mark][] = [
  ["play.types.online", "yes", "yes", "yes"],
  ["play.types.friend", "yes", "yes", "no"],
  ["play.types.spotpass", "yes", "yes", "no"],
];

async function basePatch(variant: Variant): Promise<IpsRecord[]> {
  const res = await fetch(`${import.meta.env.BASE_URL}${VARIANTS[variant]}`);
  if (!res.ok) throw new Error("base_missing");
  const records = readIps(new Uint8Array(await res.arrayBuffer()));
  if (readIdentity(records)) throw new Error("base_missing");
  return records;
}

function save(bytes: Uint8Array) {
  const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: "application/octet-stream" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "code.ips";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function VariantPicker({ value, onChange, name }: { value: Variant; onChange: (v: Variant) => void; name: string }) {
  const { t } = useTranslation();
  return (
    <fieldset className="choice">
      <legend>{t("play.create.variant")}</legend>
      {(Object.keys(VARIANTS) as Variant[]).map((v) => (
        <label key={v}>
          <input type="radio" name={name} value={v} checked={value === v} onChange={() => onChange(v)} /> {t(`play.variant.${v}`)}
        </label>
      ))}
    </fieldset>
  );
}

type Done = { identity: Identity; code: string; file: Uint8Array };

function CreateAccount({ enabled }: { enabled: boolean | undefined }) {
  const { t } = useTranslation();
  const [variant, setVariant] = useState<Variant>("jp");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Done | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const base = await basePatch(variant); // before the account: a missing file must not waste one
      const secret = newSecret();
      const { pid } = await createAzaharAccount(playerPassword(secret));
      const identity = { pid, secret };
      const file = writeIps(await applyIdentity(base, identity));
      setDone({ identity, code: await friendCode(pid), file });
      save(file);
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "";
      setError(code === "account_limit" || code === "rate_limited" ? "play.create.limit"
        : code === "accounts_disabled" ? "play.create.off" : "play.create.error");
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <>
        <div className="notice notice-info" role="status">
          <p>{t("play.create.done", { pid: done.identity.pid, code: done.code })}</p>
          <button type="button" className="btn" onClick={() => save(done.file)}>{t("play.create.again")}</button>
        </div>
        <p className="notice notice-warn">{t("play.create.keep")}</p>
      </>
    );
  }
  return (
    <>
      {enabled === false && <p className="notice notice-warn">{t("play.create.off")}</p>}
      <VariantPicker value={variant} onChange={setVariant} name="create-variant" />
      <p className="notice notice-warn">{t("play.create.keep")}</p>
      <button type="button" className="btn btn-primary" disabled={busy || enabled === false} onClick={create}>
        {busy ? t("play.create.working") : t("play.create.button")}
      </button>
      {error && <p className="notice notice-error" role="alert">{t(error)}</p>}
    </>
  );
}

function UpdatePatch() {
  const { t } = useTranslation();
  const [variant, setVariant] = useState<Variant>("jp");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState<{ kind: "info" | "error"; text: string } | null>(null);

  const build = async () => {
    if (!file) return;
    setMessage(null);
    let identity: Identity | null = null;
    try { identity = readIdentity(readIps(new Uint8Array(await file.arrayBuffer()))); } catch { /* not an IPS */ }
    if (!identity) { setMessage({ kind: "error", text: t("play.update.notPersonal") }); return; }
    try {
      save(writeIps(await applyIdentity(await basePatch(variant), identity)));
      setMessage({ kind: "info", text: t("play.update.done", { pid: identity.pid }) });
    } catch {
      setMessage({ kind: "error", text: t("play.create.error") });
    }
  };

  return (
    <>
      <p>{t("play.update.body")}</p>
      <label className="file-field">
        {t("play.update.file")}
        <input type="file" accept=".ips" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setMessage(null); }} />
      </label>
      <VariantPicker value={variant} onChange={setVariant} name="update-variant" />
      <button type="button" className="btn" disabled={!file} onClick={build}>{t("play.update.button")}</button>
      {message && <p className={`notice notice-${message.kind}`} role={message.kind === "error" ? "alert" : "status"}>{message.text}</p>}
    </>
  );
}

export default function Play() {
  const { t } = useTranslation();
  const meta = useApi<{ azahar_accounts?: boolean }>(apiUrl("/meta"));
  const [secure, setSecure] = useState(true);
  useEffect(() => setSecure(window.isSecureContext && !!crypto.subtle), []);
  const columns = ["t3ds", "azahar", "personal"] as const;

  return (
    <article className="prose play">
      <h1>{t("play.title")}</h1>
      <p className="lede">{t("play.lede")}</p>

      <section>
        <h2>{t("play.types.title")}</h2>
        <div className="table-wrap">
          <table className="list compact">
            <thead>
              <tr><th scope="col"><span className="sr-only">{t("play.types.feature")}</span></th>
                {columns.map((c) => <th key={c} scope="col">{t(`play.types.${c}`)}</th>)}</tr>
            </thead>
            <tbody>
              <tr><th scope="row">{t("play.types.patch")}</th>
                <td>{t("play.types.patchRelease")}</td><td>{t("play.types.patchRelease")}</td><td>{t("play.types.patchPersonal")}</td></tr>
              <tr><th scope="row">{t("play.types.needs")}</th>
                <td>{t("play.types.needs3ds")}</td><td>{t("play.types.needsAzahar")}</td><td>{t("play.types.needsPersonal")}</td></tr>
              {FEATURES.map(([key, ...marks]) => (
                <tr key={key}><th scope="row">{t(key)}</th>
                  {marks.map((m, i) => <td key={i}>{t(`play.types.${m}`)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>{t("play.types.note")}</p>
        <p><a href="https://github.com/Lurpigi/DQMJ3P-Online#player-guide" rel="noopener">{t("play.types.guide")}</a></p>
      </section>

      <section>
        <h2>{t("play.create.title")}</h2>
        {secure ? <CreateAccount enabled={meta.data?.azahar_accounts} /> : <p className="notice notice-error">{t("play.create.error")}</p>}
      </section>

      <section>
        <h2>{t("play.install.title")}</h2>
        <ol>
          <li>{t("play.install.step1")}</li>
          <li>{t("play.install.step2")} <code>{MODS_PATH}</code></li>
          <li>{t("play.install.step3")}</li>
          <li>{t("play.install.step4")}</li>
        </ol>
        <p>{t("play.install.gp")}</p>
      </section>

      <section>
        <h2>{t("play.update.title")}</h2>
        {secure && <UpdatePatch />}
      </section>
    </article>
  );
}
