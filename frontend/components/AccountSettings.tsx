"use client";

/**
 * AccountSettings: the /hesap page's forms — display name, sign-in methods,
 * password (change, or set one on a Google-only account), signing out other
 * devices, and deleting the account. Every change goes through the API and
 * the page refreshes from the server's answer.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  changePassword,
  deleteAccount,
  logoutOthers,
  sendVerification,
  updateProfile,
  type CurrentUser,
} from "@/services/auth";

const input =
  "mt-1 min-h-11 w-full rounded-lg border border-line-strong bg-paper px-3 text-ink placeholder:text-faint focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none";
const primary =
  "inline-flex min-h-11 items-center justify-center rounded-lg bg-ink px-4 font-semibold text-paper transition-colors hover:bg-accent disabled:opacity-50";
const card = "space-y-4 rounded-2xl border border-line bg-surface p-5 shadow-card sm:p-6";

type Status = { kind: "ok" | "error"; text: string } | null;

function Note({ status }: { status: Status }) {
  if (!status) return null;
  return (
    <p role={status.kind === "error" ? "alert" : "status"} className={`text-sm ${status.kind === "error" ? "text-bad" : "text-ok"}`}>
      {status.text}
    </p>
  );
}

function useAction() {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>(null);
  async function run(action: () => Promise<string | void>) {
    setBusy(true);
    setStatus(null);
    try {
      const text = await action();
      if (text) setStatus({ kind: "ok", text });
    } catch (e) {
      setStatus({ kind: "error", text: e instanceof Error ? e.message : "İşlem tamamlanamadı." });
    } finally {
      setBusy(false);
    }
  }
  return { busy, status, run };
}

export function AccountSettings({ user }: { user: CurrentUser }) {
  const router = useRouter();
  const profile = useAction();
  const password = useAction();
  const devices = useAction();
  const removal = useAction();
  const verification = useAction();
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className="space-y-6">
      <section aria-labelledby="profil" className={card}>
        <h2 id="profil" className="text-lg font-semibold text-ink">Profil</h2>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const name = String(new FormData(e.currentTarget).get("display_name") || "");
            void profile.run(async () => {
              await updateProfile(name);
              router.refresh();
              return "Kaydedildi.";
            });
          }}
        >
          <label className="block min-w-0 flex-1 basis-56 text-sm font-medium text-ink-2">
            Görünen ad
            <input name="display_name" defaultValue={user.display_name} required maxLength={100} autoComplete="nickname" className={input} />
          </label>
          <button disabled={profile.busy} className={primary}>
            {profile.busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </form>
        <Note status={profile.status} />
      </section>

      <section aria-labelledby="giris" className={card}>
        <h2 id="giris" className="text-lg font-semibold text-ink">Giriş yöntemleri</h2>
        <dl className="divide-y divide-line text-sm">
          <div className="flex flex-wrap justify-between gap-2 py-2.5">
            <dt className="text-muted">E-posta</dt>
            <dd className="font-semibold break-all text-ink">
              {user.email}{" "}
              <span className={user.email_verified ? "text-ok" : "text-muted"}>
                {user.email_verified ? "· doğrulandı" : "· doğrulanmadı"}
              </span>
            </dd>
          </div>
          <div className="flex flex-wrap justify-between gap-2 py-2.5">
            <dt className="text-muted">Parola</dt>
            <dd className="font-semibold text-ink">{user.has_password ? "Var" : "Yok"}</dd>
          </div>
          <div className="flex flex-wrap justify-between gap-2 py-2.5">
            <dt className="text-muted">Google</dt>
            <dd className={`font-semibold ${user.google ? "text-ok" : "text-ink"}`}>{user.google ? "Bağlı" : "Bağlı değil"}</dd>
          </div>
        </dl>
        {!user.email_verified && (
          <div className="space-y-2">
            <p className="text-sm text-muted">
              E-posta adresini doğrula: kayıt olurken gönderdiğimiz bağlantıya tıkla. Doğrulanmamış bir hesaba aynı adresin
              Google hesabıyla girilirse, güvenlik için parola kaldırılır ve diğer oturumlar kapanır.
            </p>
            <button
              type="button"
              disabled={verification.busy}
              onClick={() =>
                void verification.run(async () => {
                  await sendVerification();
                  return "Doğrulama bağlantısını gönderdik. Gelen kutunu (ve gereksiz klasörünü) kontrol et.";
                })
              }
              className={primary}
            >
              Doğrulama e-postasını gönder
            </button>
            <Note status={verification.status} />
          </div>
        )}
        {!user.google && (
          <p className="text-xs text-muted">
            Giriş sayfasında aynı e-postayla “Google ile devam et” diyerek Google hesabını bu hesaba bağlayabilirsin.
          </p>
        )}
      </section>

      <section aria-labelledby="parola" className={card}>
        <div className="space-y-1">
          <h2 id="parola" className="text-lg font-semibold text-ink">{user.has_password ? "Parolayı değiştir" : "Parola belirle"}</h2>
          <p className="text-sm text-muted">
            {user.has_password
              ? "Parolan değişince diğer cihazlardaki oturumların kapanır."
              : "Hesabının parolası yok; Google ile giriyorsun. İstersen e-postayla da girebilmek için bir parola belirleyebilirsin."}
          </p>
        </div>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const data = new FormData(form);
            void password.run(async () => {
              await changePassword(String(data.get("current_password") || ""), String(data.get("new_password") || ""));
              form.reset();
              router.refresh();
              return user.has_password ? "Parolan değişti; diğer cihazlardan çıkış yapıldı." : "Parolan belirlendi.";
            });
          }}
        >
          {user.has_password && (
            <label className="block text-sm font-medium text-ink-2">
              Mevcut parola
              <input name="current_password" type={showPassword ? "text" : "password"} required autoComplete="current-password" className={input} />
            </label>
          )}
          <label className="block text-sm font-medium text-ink-2">
            Yeni parola
            <input name="new_password" type={showPassword ? "text" : "password"} required minLength={8} maxLength={128} autoComplete="new-password" className={input} />
            <span className="mt-1 block text-xs font-normal text-muted">En az 8 karakter.</span>
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <button disabled={password.busy} className={primary}>
              {password.busy ? "Kaydediliyor…" : user.has_password ? "Parolayı değiştir" : "Parola belirle"}
            </button>
            <button type="button" onClick={() => setShowPassword((v) => !v)} aria-pressed={showPassword} className="min-h-11 rounded-lg px-2 text-sm font-semibold text-muted hover:text-ink">
              {showPassword ? "Parolaları gizle" : "Parolaları göster"}
            </button>
          </div>
        </form>
        <Note status={password.status} />
      </section>

      <section aria-labelledby="cihazlar" className={card}>
        <div className="space-y-1">
          <h2 id="cihazlar" className="text-lg font-semibold text-ink">Cihazlar</h2>
          <p className="text-sm text-muted">Başka bir telefonda ya da bilgisayarda açık kalan oturumların hepsini kapatır. Bu cihazda girişli kalırsın.</p>
        </div>
        <button
          type="button"
          disabled={devices.busy}
          onClick={() =>
            void devices.run(async () => {
              const { revoked } = await logoutOthers();
              return revoked ? `${revoked} oturum kapatıldı.` : "Başka açık oturum yoktu.";
            })
          }
          className="inline-flex min-h-11 items-center rounded-lg border border-line-strong bg-surface px-4 font-semibold text-ink transition-colors hover:border-ink/40 disabled:opacity-50"
        >
          {devices.busy ? "Kapatılıyor…" : "Diğer cihazlardan çıkış yap"}
        </button>
        <Note status={devices.status} />
      </section>

      {user.role !== "ADMIN" && (
        <section aria-labelledby="sil" className="space-y-4 rounded-2xl border border-bad/30 bg-bad-soft/40 p-5 sm:p-6">
          <div className="space-y-1">
            <h2 id="sil" className="text-lg font-semibold text-bad">Hesabı sil</h2>
            <p className="text-sm text-ink-2">
              Koleksiyonun, istek listen, fiyat alarmların ve oturumların kalıcı olarak silinir. Bu işlem geri alınamaz.
            </p>
          </div>
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              const confirm = String(new FormData(e.currentTarget).get("confirm") || "");
              void removal.run(async () => {
                await deleteAccount(confirm);
                router.replace("/");
                router.refresh();
              });
            }}
          >
            <label className="block min-w-0 flex-1 basis-56 text-sm font-medium text-ink-2">
              {user.has_password ? "Onay için parolan" : "Onay için e-posta adresin"}
              <input
                name="confirm"
                type={user.has_password ? "password" : "email"}
                required
                autoComplete={user.has_password ? "current-password" : "off"}
                placeholder={user.has_password ? "" : user.email}
                className={input}
              />
            </label>
            <button disabled={removal.busy} className="inline-flex min-h-11 items-center justify-center rounded-lg bg-bad px-4 font-semibold text-paper transition-colors hover:opacity-90 disabled:opacity-50">
              {removal.busy ? "Siliniyor…" : "Hesabımı sil"}
            </button>
          </form>
          <Note status={removal.status} />
        </section>
      )}
    </div>
  );
}
