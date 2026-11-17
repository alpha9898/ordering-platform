import { useCallback, useEffect, useState } from "react";
import { Download, FileSpreadsheet, Pencil, Plus, Trash2, Upload } from "lucide-react";
import { ApiError, api, del, get, patch, post, put } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { money } from "../../lib/format";
import { Badge, Button, Card, Field, Input, Modal, Spinner, Switch, inputCls, useToast } from "../../components/ui";

type Variant = { id?: number; name: string | null; price: number; available: boolean };
type Item = { id: number; category_id: number; name: string; description: string | null; available: boolean; variants: Variant[] };
type Category = { id: number; name: string; active: boolean; sort: number; items: Item[]; addons: { addon_id: number; price_override: number | null }[] };
type Addon = { id: number; name: string; price: number; available: boolean };
type MenuT = { categories: Category[]; addons: Addon[] };

export default function MenuEditor() {
  const { me } = useAuth();
  const toast = useToast();
  const [menu, setMenu] = useState<MenuT | null>(null);
  const [itemModal, setItemModal] = useState<Partial<Item> | null>(null);
  const [catModal, setCatModal] = useState<Partial<Category> | null>(null);
  const [addonModal, setAddonModal] = useState<Partial<Addon> | null>(null);
  const [importing, setImporting] = useState(false);
  const manage = !!me?.can_manage;

  const load = useCallback(() => get<MenuT>("/dash/menu").then(setMenu), []);
  useEffect(() => {
    load();
  }, [load]);

  const toggle = async (path: string, available: boolean, apply: (m: MenuT) => void) => {
    setMenu((m) => {
      if (!m) return m;
      const copy = structuredClone(m);
      apply(copy);
      return copy;
    });
    try {
      await patch(path, { available });
      toast(available ? "متاح تاني ✅" : "اتعلّم إنه خلص — البوت مش هيعرضه");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "حصلت مشكلة", "danger");
      load();
    }
  };

  if (!menu)
    return (
      <div className="grid h-40 place-items-center text-muted">
        <Spinner />
      </div>
    );

  return (
    <div className="space-y-4">
      {manage ? (
        <div className="flex flex-wrap gap-2">
          <Button tone="primary" onClick={() => setItemModal({ category_id: menu.categories[0]?.id, variants: [{ name: null, price: 0, available: true }] })} disabled={!menu.categories.length}>
            <Plus className="size-4" /> صنف جديد
          </Button>
          <Button onClick={() => setCatModal({ active: true, addons: [] })}>
            <Plus className="size-4" /> قسم جديد
          </Button>
          <Button onClick={() => setAddonModal({ price: 0 })}>
            <Plus className="size-4" /> إضافة جديدة
          </Button>
          <div className="ms-auto flex gap-2">
            <a href="/api/dash/menu/export.xlsx">
              <Button tone="ghost">
                <Download className="size-4" /> تحميل Excel
              </Button>
            </a>
            <Button tone="ghost" onClick={() => setImporting(true)}>
              <Upload className="size-4" /> رفع Excel
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted">علّم على الصنف اللي خلص، والبوت هيخفيه فورًا من المنيو.</p>
      )}

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          {menu.categories.map((c) => (
            <Card key={c.id} className={c.active ? "" : "opacity-60"}>
              <div className="flex items-center gap-3 border-b border-line px-4 py-3">
                <h3 className="font-bold">{c.name}</h3>
                <Badge>{c.items.length} صنف</Badge>
                {!c.active ? <Badge tone="danger">مخفي</Badge> : null}
                <div className="ms-auto flex items-center gap-2">
                  {manage ? (
                    <Button size="sm" tone="ghost" onClick={() => setCatModal(c)} aria-label={`تعديل ${c.name}`}>
                      <Pencil className="size-4" />
                    </Button>
                  ) : null}
                </div>
              </div>
              <ul className="divide-y divide-line">
                {c.items.map((it) => (
                  <li key={it.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                    <div className="min-w-40 flex-1">
                      <div className={`font-semibold ${it.available ? "" : "text-muted line-through"}`}>{it.name}</div>
                      <div className="mt-1 flex flex-wrap gap-1.5 text-xs">
                        {it.variants.map((v) => (
                          <span key={v.id} className={`inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 ${v.available ? "" : "text-muted line-through"}`}>
                            {v.name ? `${v.name} ` : ""}
                            <span className="num">{money(v.price)}</span>
                            {it.variants.length > 1 ? (
                              <input
                                type="checkbox"
                                className="accent-[var(--ok)]"
                                checked={v.available}
                                aria-label={`${it.name} ${v.name} متاح`}
                                onChange={(e) =>
                                  toggle(`/dash/variants/${v.id}`, e.target.checked, (m) => {
                                    m.categories.flatMap((x) => x.items).find((x) => x.id === it.id)!.variants.find((x) => x.id === v.id)!.available = e.target.checked;
                                  })
                                }
                              />
                            ) : null}
                          </span>
                        ))}
                      </div>
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                      <span className={it.available ? "text-ok" : "text-danger"}>{it.available ? "متاح" : "خلص"}</span>
                      <Switch
                        checked={it.available}
                        label={`${it.name} متاح`}
                        onChange={(v) =>
                          toggle(`/dash/items/${it.id}`, v, (m) => {
                            m.categories.flatMap((x) => x.items).find((x) => x.id === it.id)!.available = v;
                          })
                        }
                      />
                    </label>
                    {manage ? (
                      <Button size="sm" tone="ghost" onClick={() => setItemModal(it)} aria-label={`تعديل ${it.name}`}>
                        <Pencil className="size-4" />
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>

        <Card className="h-fit">
          <div className="border-b border-line px-4 py-3 font-bold">الإضافات</div>
          <ul className="divide-y divide-line">
            {menu.addons.map((a) => (
              <li key={a.id} className="flex items-center gap-3 px-4 py-2">
                <span className={`flex-1 text-sm ${a.available ? "" : "text-muted line-through"}`}>{a.name}</span>
                <span className="num text-sm text-muted">+{money(a.price)}</span>
                <Switch
                  checked={a.available}
                  label={`${a.name} متاح`}
                  onChange={(v) =>
                    toggle(`/dash/addons/${a.id}`, v, (m) => {
                      m.addons.find((x) => x.id === a.id)!.available = v;
                    })
                  }
                />
                {manage ? (
                  <button onClick={() => setAddonModal(a)} className="text-muted hover:text-fg" aria-label={`تعديل ${a.name}`}>
                    <Pencil className="size-4" />
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {itemModal ? <ItemModal item={itemModal} categories={menu.categories} onClose={() => setItemModal(null)} onSaved={load} /> : null}
      {catModal ? <CategoryModal cat={catModal} addons={menu.addons} onClose={() => setCatModal(null)} onSaved={load} /> : null}
      {addonModal ? <AddonModal addon={addonModal} categories={menu.categories} onClose={() => setAddonModal(null)} onSaved={load} /> : null}
      <ImportModal open={importing} onClose={() => setImporting(false)} onApplied={load} />
    </div>
  );
}

function useSaver(onClose: () => void, onSaved: () => void) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>, msg = "اتحفظ ✅") => {
    setBusy(true);
    try {
      await fn();
      toast(msg);
      onSaved();
      onClose();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "حصلت مشكلة", "danger");
    } finally {
      setBusy(false);
    }
  };
  return { busy, run };
}

function ItemModal({ item, categories, onClose, onSaved }: { item: Partial<Item>; categories: Category[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({
    name: item.name ?? "",
    description: item.description ?? "",
    category_id: item.category_id ?? categories[0]?.id,
    variants: (item.variants ?? []).map((v) => ({ ...v })),
  });
  const { busy, run } = useSaver(onClose, onSaved);
  const setVar = (i: number, patchV: Partial<Variant>) => setF({ ...f, variants: f.variants.map((v, k) => (k === i ? { ...v, ...patchV } : v)) });

  const save = () =>
    run(async () => {
      const variants = f.variants.map((v) => ({ ...v, name: v.name?.trim() || null, price: Number(v.price) }));
      if (!item.id) {
        await post("/dash/items", { name: f.name, description: f.description || null, category_id: f.category_id, variants });
        return;
      }
      await patch(`/dash/items/${item.id}`, { name: f.name, description: f.description || null, category_id: f.category_id });
      const before = item.variants ?? [];
      for (const v of variants) {
        if (v.id) await patch(`/dash/variants/${v.id}`, { name: v.name, price: v.price, available: v.available });
        else await post(`/dash/items/${item.id}/variants`, v);
      }
      for (const old of before) if (!variants.some((v) => v.id === old.id)) await del(`/dash/variants/${old.id}`);
    });

  return (
    <Modal open onClose={onClose} title={item.id ? `تعديل ${item.name}` : "صنف جديد"}>
      <div className="space-y-4">
        <Field label="اسم الصنف">
          <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} maxLength={80} />
        </Field>
        <Field label="القسم">
          <select className={inputCls} value={f.category_id} onChange={(e) => setF({ ...f, category_id: Number(e.target.value) })}>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="وصف (اختياري)">
          <Input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} maxLength={300} />
        </Field>
        <div>
          <div className="mb-2 text-sm font-semibold">الأسعار</div>
          <p className="mb-2 text-xs text-muted">صنف بسعر واحد: سيب اسم الحجم فاضي. فردي/دبل: سطرين.</p>
          <div className="space-y-2">
            {f.variants.map((v, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input placeholder="الحجم (فردي، دبل…)" value={v.name ?? ""} onChange={(e) => setVar(i, { name: e.target.value })} className="flex-1" />
                <Input type="number" min={0} value={v.price} onChange={(e) => setVar(i, { price: Number(e.target.value) })} className="num w-24" aria-label="السعر" />
                <Switch checked={v.available} onChange={(x) => setVar(i, { available: x })} label="متاح" />
                <button
                  onClick={() => setF({ ...f, variants: f.variants.filter((_, k) => k !== i) })}
                  disabled={f.variants.length <= 1}
                  className="p-1 text-muted hover:text-danger disabled:opacity-30"
                  aria-label="شيل السعر"
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
            ))}
          </div>
          <Button size="sm" tone="ghost" className="mt-2" onClick={() => setF({ ...f, variants: [...f.variants, { name: "", price: 0, available: true }] })}>
            <Plus className="size-4" /> سعر/حجم تاني
          </Button>
        </div>
        <div className="flex gap-2 pt-2">
          <Button tone="primary" className="flex-1" loading={busy} disabled={!f.name.trim() || !f.variants.length} onClick={save}>
            حفظ
          </Button>
          {item.id ? (
            <Button tone="danger" onClick={() => confirm(`مسح ${item.name}؟ الطلبات القديمة مش هتتأثر.`) && run(() => del(`/dash/items/${item.id}`), "اتمسح")}>
              <Trash2 className="size-4" /> مسح
            </Button>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}

function CategoryModal({ cat, addons, onClose, onSaved }: { cat: Partial<Category>; addons: Addon[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ name: cat.name ?? "", active: cat.active ?? true, sort: cat.sort ?? 0 });
  const [links, setLinks] = useState<Record<number, { on: boolean; override: string }>>(() =>
    Object.fromEntries(addons.map((a) => {
      const l = cat.addons?.find((x) => x.addon_id === a.id);
      return [a.id, { on: !!l, override: l?.price_override != null ? String(l.price_override) : "" }];
    })),
  );
  const { busy, run } = useSaver(onClose, onSaved);
  const save = () =>
    run(async () => {
      let id = cat.id;
      if (!id) id = (await post("/dash/categories", f)).id;
      else await patch(`/dash/categories/${id}`, f);
      await put(
        `/dash/categories/${id}/addons`,
        Object.entries(links)
          .filter(([, l]) => l.on)
          .map(([aid, l]) => ({ addon_id: Number(aid), price_override: l.override === "" ? null : Number(l.override) })),
      );
    });
  return (
    <Modal open onClose={onClose} title={cat.id ? `تعديل ${cat.name}` : "قسم جديد"}>
      <div className="space-y-4">
        <Field label="اسم القسم">
          <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} maxLength={60} />
        </Field>
        <div className="flex gap-4">
          <Field label="الترتيب">
            <Input type="number" value={f.sort} onChange={(e) => setF({ ...f, sort: Number(e.target.value) })} className="num w-24" />
          </Field>
          <label className="flex items-center gap-2 pt-6 text-sm">
            <Switch checked={f.active} onChange={(v) => setF({ ...f, active: v })} /> ظاهر للعملاء
          </label>
        </div>
        <div>
          <div className="mb-2 text-sm font-semibold">الإضافات المتاحة للقسم ده</div>
          <div className="max-h-64 space-y-1 overflow-y-auto rounded-xl border border-line p-2">
            {addons.map((a) => (
              <div key={a.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={links[a.id]?.on} onChange={(e) => setLinks({ ...links, [a.id]: { ...links[a.id], on: e.target.checked } })} id={`ad-${a.id}`} className="size-4 accent-[var(--primary)]" />
                <label htmlFor={`ad-${a.id}`} className="flex-1">
                  {a.name} <span className="text-muted">(+{money(a.price)})</span>
                </label>
                {links[a.id]?.on ? (
                  <Input
                    placeholder="سعر خاص"
                    type="number"
                    value={links[a.id].override}
                    onChange={(e) => setLinks({ ...links, [a.id]: { ...links[a.id], override: e.target.value } })}
                    className="num h-8 w-24"
                  />
                ) : null}
              </div>
            ))}
          </div>
        </div>
        <div className="flex gap-2 pt-2">
          <Button tone="primary" className="flex-1" loading={busy} disabled={!f.name.trim()} onClick={save}>
            حفظ
          </Button>
          {cat.id ? (
            <Button tone="danger" onClick={() => confirm(`مسح قسم ${cat.name}؟`) && run(() => del(`/dash/categories/${cat.id}`), "اتمسح")}>
              <Trash2 className="size-4" />
            </Button>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}

function AddonModal({ addon, categories, onClose, onSaved }: { addon: Partial<Addon>; categories: Category[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ name: addon.name ?? "", price: addon.price ?? 0 });
  const [cats, setCats] = useState<number[]>([]);
  const { busy, run } = useSaver(onClose, onSaved);
  const save = () =>
    run(() => (addon.id ? patch(`/dash/addons/${addon.id}`, f) : post("/dash/addons", { ...f, category_ids: cats })));
  return (
    <Modal open onClose={onClose} title={addon.id ? `تعديل ${addon.name}` : "إضافة جديدة"}>
      <div className="space-y-4">
        <Field label="اسم الإضافة">
          <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} maxLength={60} />
        </Field>
        <Field label="السعر">
          <Input type="number" min={0} value={f.price} onChange={(e) => setF({ ...f, price: Number(e.target.value) })} className="num w-32" />
        </Field>
        {!addon.id ? (
          <div>
            <div className="mb-2 text-sm font-semibold">تتضاف على أنهي أقسام؟</div>
            <div className="flex flex-wrap gap-2">
              {categories.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setCats(cats.includes(c.id) ? cats.filter((x) => x !== c.id) : [...cats, c.id])}
                  className={`rounded-full border px-3 py-1 text-sm ${cats.includes(c.id) ? "border-primary bg-primary-soft text-primary" : "border-line"}`}
                >
                  {c.name}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted">الأقسام اللي الإضافة دي متاحة فيها بتتعدل من إعدادات كل قسم.</p>
        )}
        <div className="flex gap-2 pt-2">
          <Button tone="primary" className="flex-1" loading={busy} disabled={!f.name.trim()} onClick={save}>
            حفظ
          </Button>
          {addon.id ? (
            <Button tone="danger" onClick={() => confirm(`مسح ${addon.name}؟`) && run(() => del(`/dash/addons/${addon.id}`), "اتمسح")}>
              <Trash2 className="size-4" />
            </Button>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}

type Preview = {
  categories: number;
  items: number;
  variants: number;
  addons: number;
  error_count: number;
  errors: { sheet: string; row: number; message: string }[];
  preview: { category: string; items: { name: string; variants: { name: string | null; price: number }[] }[] }[];
};

function ImportModal({ open, onClose, onApplied }: { open: boolean; onClose: () => void; onApplied: () => void }) {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);

  const upload = async (apply: boolean) => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    try {
      const r = await api<Preview>(`/dash/menu/import?apply=${apply}`, { method: "POST", form });
      if (apply) {
        toast("المنيو اتحدّث من الملف ✅");
        onApplied();
        close();
      } else setPreview(r);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "حصلت مشكلة", "danger");
    } finally {
      setBusy(false);
    }
  };
  const close = () => {
    setFile(null);
    setPreview(null);
    onClose();
  };

  return (
    <Modal open={open} onClose={close} title="رفع المنيو من Excel" wide>
      <ol className="mb-4 list-inside list-decimal space-y-1 text-sm text-muted">
        <li>حمّل ملف Excel (فيه المنيو الحالي بنفس الشكل المطلوب).</li>
        <li>عدّل أو ضيف أصناف وأسعار. صنف فردي/دبل = سطرين.</li>
        <li>ارفعه هنا، راجع المعاينة، وبعدين طبّق.</li>
      </ol>
      <label className="mb-4 flex cursor-pointer items-center gap-3 rounded-xl border-2 border-dashed border-line p-4 hover:border-primary">
        <FileSpreadsheet className="size-8 text-ok" />
        <span className="flex-1 text-sm">{file ? file.name : "اختار ملف .xlsx"}</span>
        <input
          type="file"
          accept=".xlsx"
          className="sr-only"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setPreview(null);
          }}
        />
      </label>
      {!preview ? (
        <Button tone="primary" className="w-full" disabled={!file} loading={busy} onClick={() => upload(false)}>
          معاينة
        </Button>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-2 text-center">
            {[
              ["أقسام", preview.categories],
              ["أصناف", preview.items],
              ["أسعار", preview.variants],
              ["إضافات", preview.addons],
            ].map(([l, n]) => (
              <div key={l} className="rounded-xl bg-surface-2 p-3">
                <div className="num text-xl font-bold">{n}</div>
                <div className="text-xs text-muted">{l}</div>
              </div>
            ))}
          </div>
          {preview.error_count ? (
            <div className="rounded-xl border border-danger bg-danger-soft p-3 text-sm text-danger">
              <div className="mb-2 font-bold">{preview.error_count} غلطة لازم تتصلح الأول:</div>
              <ul className="max-h-48 space-y-1 overflow-y-auto">
                {preview.errors.map((e, i) => (
                  <li key={i}>
                    شيت {e.sheet}، سطر {e.row}: {e.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="max-h-64 overflow-y-auto rounded-xl border border-line p-3 text-sm">
              {preview.preview.map((c) => (
                <div key={c.category} className="mb-2">
                  <div className="font-bold">{c.category}</div>
                  <div className="text-muted">{c.items.map((i) => `${i.name} (${i.variants.map((v) => (v.name ? `${v.name} ${v.price}` : v.price)).join(" / ")})`).join("، ")}</div>
                </div>
              ))}
            </div>
          )}
          <p className="text-xs text-muted">التطبيق بيستبدل المنيو كله. الطلبات القديمة مش هتتأثر.</p>
          <Button tone="primary" className="w-full" disabled={!!preview.error_count} loading={busy} onClick={() => upload(true)}>
            طبّق المنيو الجديد
          </Button>
        </div>
      )}
    </Modal>
  );
}
