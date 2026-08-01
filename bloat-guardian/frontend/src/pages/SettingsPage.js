import { useEffect, useState } from "react";
import { Eye, EyeOff, KeyRound, Save, Server } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/sonner";
import AssumptionsEditor from "@/components/AssumptionsEditor";
import { apiError, endpoints } from "@/lib/api";

const KEY_FIELDS = [
  { key: "anthropic_api_key", provider: "anthropic", label: "Anthropic API key", placeholder: "sk-ant-..." },
  { key: "gemini_api_key", provider: "gemini", label: "Google Gemini API key", placeholder: "AIza..." },
  { key: "openai_api_key", provider: "openai", label: "OpenAI API key", placeholder: "sk-..." },
  { key: "github_token", provider: "github", label: "GitHub personal access token", placeholder: "github_pat_..." },
  { key: "bitbucket_token", provider: "bitbucket", label: "Bitbucket access token", placeholder: "Bitbucket token" },
];

export default function SettingsPage() {
  const [settings, setSettings] = useState(null);
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState("claude-opus-4-7");
  const [usePlatformKey, setUsePlatformKey] = useState(true);
  const [autoDrafts, setAutoDrafts] = useState(5);
  const [keys, setKeys] = useState({});
  const [reveal, setReveal] = useState({});
  const [saving, setSaving] = useState(false);

  const load = () => {
    endpoints
      .settings()
      .then((res) => {
        setSettings(res.data);
        setProvider(res.data.llm_provider);
        setModel(res.data.llm_model);
        setUsePlatformKey(res.data.use_platform_key);
        setAutoDrafts(res.data.auto_draft_count);
      })
      .catch((err) => toast.error(apiError(err, "Could not load settings")));
  };

  useEffect(load, []);

  const save = async () => {
    setSaving(true);
    try {
      const patch = {
        llm_provider: provider,
        llm_model: model,
        use_platform_key: usePlatformKey,
        auto_draft_count: Number(autoDrafts),
      };
      KEY_FIELDS.forEach((f) => {
        if (keys[f.key] !== undefined && keys[f.key] !== "") patch[f.key] = keys[f.key];
      });
      const res = await endpoints.saveSettings(patch);
      setSettings(res.data);
      setKeys({});
      toast.success("Settings saved");
    } catch (err) {
      toast.error(apiError(err, "Could not save settings"));
    } finally {
      setSaving(false);
    }
  };

  const clearKey = async (field) => {
    try {
      const res = await endpoints.saveSettings({ [field]: "" });
      setSettings(res.data);
      toast.success("Key removed");
    } catch (err) {
      toast.error(apiError(err, "Could not remove that key"));
    }
  };

  if (!settings) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const models = settings.provider_models?.[provider] || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-h1 font-heading">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Choose the model that writes your optimised drafts, add your own keys, and control the savings
          maths.
        </p>
      </div>

      <Card className="rounded-xl border border-border bg-card p-5 shadow-[var(--shadow-md)]">
        <div className="flex items-start gap-3">
          <Server className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div className="min-w-0 flex-1">
            <h2 className="font-heading text-lg font-bold">Draft generation model</h2>
            <p className="text-xs text-muted-foreground">
              Drafts are refined rewrites of files that already exist in your repository.
            </p>

            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <Label className="text-xs">Provider</Label>
                <Select
                  value={provider}
                  onValueChange={(v) => {
                    setProvider(v);
                    const first = settings.provider_models?.[v]?.[0];
                    if (first) setModel(first);
                  }}
                >
                  <SelectTrigger className="mt-1 h-9" data-testid="settings-provider-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.keys(settings.provider_models || {}).map((p) => (
                      <SelectItem key={p} value={p}>
                        {p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Model</Label>
                <Select value={model} onValueChange={setModel}>
                  <SelectTrigger className="mt-1 h-9" data-testid="settings-model-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map((m) => (
                      <SelectItem key={m} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Drafts written automatically per scan (0 to 25)</Label>
                <Input
                  type="number"
                  min={0}
                  max={25}
                  className="mt-1 h-9"
                  value={autoDrafts}
                  onChange={(e) => setAutoDrafts(e.target.value)}
                  data-testid="settings-auto-draft-input"
                />
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-secondary p-3">
              <div>
                <p className="text-sm font-medium">Use the platform managed key</p>
                <p className="text-xs text-muted-foreground">
                  {settings.platform_key_available
                    ? "A universal key is configured on this server. Turn this off to use your own key instead."
                    : "No platform key is configured. Add your own key below."}
                </p>
              </div>
              <Switch
                checked={usePlatformKey}
                onCheckedChange={setUsePlatformKey}
                data-testid="settings-use-platform-key-switch"
              />
            </div>

            <Button className="mt-4" onClick={save} disabled={saving} data-testid="settings-save-button">
              <Save className="mr-1.5 h-3.5 w-3.5" /> {saving ? "Saving" : "Save settings"}
            </Button>
          </div>
        </div>
      </Card>

      <Card className="rounded-xl border border-border bg-card p-5 shadow-[var(--shadow-md)]">
        <div className="flex items-start gap-3">
          <KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div className="min-w-0 flex-1">
            <h2 className="font-heading text-lg font-bold">API keys and tokens</h2>
            <p className="text-xs text-muted-foreground">
              Stored on this server only and never shown back in full. Repository tokens raise import rate
              limits.
            </p>
            <div className="mt-4 space-y-3">
              {KEY_FIELDS.map((f) => {
                const info = settings.keys?.[f.provider] || {};
                return (
                  <div key={f.key} className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
                    <div>
                      <Label htmlFor={f.key} className="text-xs">
                        {f.label}
                        {info.has_key ? (
                          <span className="ml-2 font-mono text-[11px] text-muted-foreground">
                            saved: {info.masked}
                          </span>
                        ) : (
                          <span className="ml-2 text-[11px] text-muted-foreground">not set</span>
                        )}
                      </Label>
                      <div className="relative mt-1">
                        <Input
                          id={f.key}
                          data-testid={
                            f.provider === "github"
                              ? "settings-github-pat-input"
                              : `settings-api-key-input-${f.provider}`
                          }
                          type={reveal[f.key] ? "text" : "password"}
                          className="h-9 pr-10"
                          placeholder={f.placeholder}
                          value={keys[f.key] ?? ""}
                          onChange={(e) => setKeys({ ...keys, [f.key]: e.target.value })}
                        />
                        <button
                          type="button"
                          aria-label={reveal[f.key] ? "Hide value" : "Show value"}
                          className="absolute right-2 top-2 text-muted-foreground"
                          onClick={() => setReveal({ ...reveal, [f.key]: !reveal[f.key] })}
                        >
                          {reveal[f.key] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                      </div>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="h-9"
                      disabled={!info.has_key}
                      onClick={() => clearKey(f.key)}
                      data-testid={`settings-clear-key-${f.provider}`}
                    >
                      Remove
                    </Button>
                  </div>
                );
              })}
            </div>
            <Button className="mt-4" onClick={save} disabled={saving} data-testid="settings-save-keys-button">
              <Save className="mr-1.5 h-3.5 w-3.5" /> Save keys
            </Button>
          </div>
        </div>
      </Card>

      <AssumptionsEditor compactMode onSaved={(s) => setSettings(s)} />
    </div>
  );
}
