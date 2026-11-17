import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { ApiError, get, post } from "../lib/api";
import { useAuth, type Me } from "../lib/auth";
import { Button, Card, Field, Input, Spinner } from "../components/ui";

export default function Login() {
  const { me, setMe } = useAuth();
  const nav = useNavigate();
  const [setup, setSetup] = useState<boolean | null>(null);
  const [form, setForm] = useState({ username: "", password: "", confirm: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<{ needs_setup: boolean }>("/setup")
      .then((r) => setSetup(r.needs_setup))
      .catch(() => setSetup(false));
  }, []);

  if (me) return <Navigate to={me.is_super && !me.restaurant ? "/admin" : "/dashboard"} replace />;
  if (setup === null)
    return (
      <div className="grid min-h-dvh place-items-center text-muted">
        <Spinner />
      </div>
    );

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    if (setup && form.password !== form.confirm) return setErr("كلمتين السر مش زي بعض");
    setBusy(true);
    try {
      const m = await post<Me>(setup ? "/setup" : "/auth/login", { username: form.username, password: form.password });
      setMe(m);
      nav(m.is_super ? "/admin" : "/dashboard", { replace: true });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "حصلت مشكلة");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <Card className="w-full max-w-sm p-6">
        <div className="mb-6 flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="size-10" />
          <div>
            <h1 className="text-lg font-bold">{setup ? "إعداد أول مرة" : "تسجيل الدخول"}</h1>
            <p className="text-sm text-muted">{setup ? "اعمل حساب الإدارة الرئيسي للمنصة" : "داشبورد المطعم ولوحة الإدارة"}</p>
          </div>
        </div>
        {setup ? (
          <p className="mb-4 rounded-xl bg-warn-soft px-3 py-2 text-sm text-warn">
            الصفحة دي بتظهر مرة واحدة بس. أول حساب يتعمل هنا هو صاحب المنصة، وبعده الصفحة بتتقفل.
          </p>
        ) : null}
        <form onSubmit={submit} className="space-y-4">
          <Field label="اسم المستخدم" hint={setup ? "حروف إنجليزي صغيرة وأرقام" : undefined}>
            <Input dir="ltr" autoComplete="username" required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase() })} />
          </Field>
          <Field label="كلمة السر" hint={setup ? "10 حروف على الأقل" : undefined}>
            <Input
              dir="ltr"
              type="password"
              autoComplete={setup ? "new-password" : "current-password"}
              required
              minLength={setup ? 10 : undefined}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </Field>
          {setup ? (
            <Field label="تأكيد كلمة السر">
              <Input dir="ltr" type="password" autoComplete="new-password" required value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
            </Field>
          ) : null}
          {err ? <p className="text-sm text-danger">{err}</p> : null}
          <Button tone="primary" size="lg" className="w-full" loading={busy}>
            {setup ? "إنشاء الحساب والدخول" : "دخول"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
