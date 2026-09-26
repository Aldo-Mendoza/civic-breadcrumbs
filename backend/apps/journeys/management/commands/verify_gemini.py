"""
Live verification of the configured Gemini credentials and model.

An operational command, in the same family as ``seed_demo.py`` -- **never**
invoked by ``manage.py test`` or CI, and never touches the database. It exists
because two failure modes are otherwise invisible until a demo:

1. **A dead model id.** Google retires and renames Gemini models on a schedule
   this codebase has no way to track; trusting a hardcoded default is trusting a
   guess. This command asks the API itself, live, which model ids are actually
   current, rather than the other way around.
2. **A misconfigured key.** A key can be well-formed and still be the wrong
   *kind* of credential (e.g. a Cloud project key rather than a Generative
   Language API key), or be exhausted on a free-tier daily quota. Either shows
   up here with a clear message instead of a mysterious ``degraded: true`` in
   production.

This command spends real API quota. Run it deliberately, not routinely.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from common.exceptions import AIInvalidOutput, AIUnavailable
from services.ai.gemini import GeminiAIService


def _mask(key):
    if not key or len(key) < 10:
        return "(not set)" if not key else "(too short to mask safely)"
    return key[:6] + "..." + key[-4:]


class Command(BaseCommand):
    help = (
        "Live-check the configured Gemini API key and model, then exercise "
        "all four AIService methods with synthetic data. Spends real API "
        "quota -- never run from tests or CI."
    )

    def handle(self, *args, **options):
        if not settings.AI_LIVE_TESTS:
            self.stdout.write(
                self.style.WARNING(
                    "AI_LIVE_TESTS is not set to true, so this command will not "
                    "spend real API quota. Set AI_LIVE_TESTS=true in .env if you "
                    "mean to run this deliberately."
                )
            )
            return
        if not settings.AI_ENABLED:
            self.stdout.write(
                self.style.WARNING("AI_ENABLED is false. Nothing to verify.")
            )
            return
        if not settings.GEMINI_API_KEY:
            self.stdout.write(
                self.style.WARNING("No GEMINI_API_KEY is configured. Nothing to verify.")
            )
            return

        self.stdout.write("Configured model: " + settings.GEMINI_MODEL)
        self.stdout.write("Key (masked):     " + _mask(settings.GEMINI_API_KEY))
        self.stdout.write("")

        self._check_model_catalog()
        self.stdout.write("")
        self._exercise_all_methods()
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "This command spent real API quota. It is never run by "
                "`manage.py test` -- that suite forces AI off regardless of "
                "what is in .env (config/settings/base.py: RUNNING_TESTS), so "
                "it stays free, fast and offline no matter who runs it."
            )
        )

    # -- steps ---------------------------------------------------------------

    def _check_model_catalog(self):
        """
        Confirm the configured model id is actually live right now.

        Given how quickly Gemini model ids get retired, this is the only
        trustworthy source of truth -- more trustworthy than any hardcoded
        default in this codebase, including the one in config/settings/base.py.
        """
        self.stdout.write("--- Checking the live model catalog ---")
        try:
            from google import genai
        except ImportError as exc:
            self.stdout.write(self.style.ERROR("google-genai is not installed: " + str(exc)))
            return

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        try:
            names = []
            flash_like = []
            for model in client.models.list():
                name = getattr(model, "name", "") or ""
                names.append(name)
                if "flash" in name.lower():
                    flash_like.append(name)
        except Exception as exc:
            self.stdout.write(self.style.ERROR("Could not list models: " + str(exc)[:400]))
            return

        configured = settings.GEMINI_MODEL
        found = any(configured in name for name in names)
        if found:
            self.stdout.write(self.style.SUCCESS(
                "'{model}' is present in the live catalog.".format(model=configured)
            ))
        else:
            self.stdout.write(self.style.ERROR(
                "'{model}' was NOT found in the live catalog. It may have "
                "been retired.".format(model=configured)
            ))
            self.stdout.write("Some current flash-tier candidates:")
            for name in flash_like[:8]:
                self.stdout.write("  - " + name)
            self.stdout.write(
                "Update GEMINI_MODEL in .env if one of these is a better fit. "
                "This command does not change any configuration itself."
            )

    def _exercise_all_methods(self):
        """
        Call every AIService method directly against GeminiAIService (not
        through AIGateway, so a live call is guaranteed rather than silently
        skipped by the fallback). Synthetic data only (CLAUDE.md §29/§30).
        """
        self.stdout.write("--- Exercising all four AI operations live ---")
        service = GeminiAIService()
        known_organizations = [
            {
                "name": "Immigration, Refugees and Citizenship Canada",
                "short_name": "IRCC",
                "aliases": ["IRCC", "immigration canada"],
            }
        ]

        self._try(
            "extract_journey",
            lambda: service.extract_journey(
                "I applied to extend my study permit and I'm not sure what to do next."
            ),
        )
        self._try(
            "extract_breadcrumb",
            lambda: service.extract_breadcrumb(
                "I called IRCC today. They said my application is still "
                "processing and told me not to submit another one.",
                {
                    "journey_title": "Study Permit Extension",
                    "journey_goal": "Extend my study permit",
                    "known_organizations": known_organizations,
                    "today": "2026-01-01",
                },
            ),
        )
        self._try(
            "summarize_stuck_state",
            lambda: service.summarize_stuck_state(
                {
                    "summary": (
                        "You submitted your application and later recorded "
                        "that IRCC said it remained under processing."
                    )
                }
            ),
        )
        self._try(
            "generate_handoff",
            lambda: service.generate_handoff(
                {
                    "summary": (
                        "Application submitted Sept 18. IRCC contacted Sept "
                        "24, said processing, told not to resubmit."
                    )
                }
            ),
        )

    def _try(self, label, call):
        try:
            result = call()
            self.stdout.write(self.style.SUCCESS(label + ": OK"))
            for key, value in result.model_dump().items():
                self.stdout.write("    {key}: {value!r}".format(key=key, value=value))
        except (AIUnavailable, AIInvalidOutput) as exc:
            self.stdout.write(self.style.ERROR(
                "{label}: {code} -- {message}".format(
                    label=label, code=exc.code, message=exc.detail
                )
            ))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(
                "{label}: unexpected {kind} -- {message}".format(
                    label=label, kind=type(exc).__name__, message=str(exc)[:300]
                )
            ))
