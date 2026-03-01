# --- Import Django ---
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
from django.views import View

# --- Import App-Content ---
from staff.mixin import StaffAdminRequiredMixin, StaffRequiredMixin
from chat.views import ChatView
#--------------
from .models import EvalItem
from .models import EvalRun as EvalRunModel,  EvalResult, HumanRating
from .eval_utils import is_semantically_correct_v2
# --- Import Sonstige Module ---
import json


# --- Views ---
class EvalRunAPIView(APIView):
    permission_classes = [IsAuthenticated, StaffAdminRequiredMixin]
    def post(self, request):
        limit = int(request.data.get("limit", 20))
        limit = max(1, min(limit, 50))
        threshold = float(request.data.get("threshold", 0.80))
        items = list(EvalItem.objects.all()[:limit])
        correct = 0

        for it in items:
            # Fake-Request für ChatView bauen
            req = type("obj", (), {"data": {"message": it.question}, "user": request.user})
            resp = ChatView().post(req)

            status_ok = 200 <= resp.status_code < 300
            data = resp.data or {}
            sources_ok = bool(data.get("sources"))

            answer_text = (
                data.get("answer")
                or data.get("message")
                or data.get("content")
                or ""
            )

            expected_hint = getattr(it, "expected_hint", None)
            # Semantischer Vergleich
            if expected_hint:
                semantic_ok, similarity = is_semantically_correct_v2(answer_text, expected_hint, threshold=threshold)
            else:
                semantic_ok, similarity = False, 0.0

            ok = status_ok and sources_ok and semantic_ok

            it.last_accuracy = bool(ok)
            it.save(update_fields=["last_accuracy"])
            correct += 1 if ok else 0

        return Response({
            "count": len(items),
            "accuracy": (correct / len(items) if items else 0),
            "threshold": threshold,
            "limit": limit,
        })


class QualityRunStatusView(StaffRequiredMixin, View):
    def get(self, request, run_id):
        run = EvalRunModel.objects.get(id=run_id)
        percent = int((run.evaluated / run.total) * 100) if run.total else 0
        return JsonResponse({
            "run_id": run.id,
            "status": run.status,
            "total": run.total,
            "evaluated_count": run.evaluated,
            "evaluated_percent": percent,
            "accuracy": round((run.accuracy_auto or 0) * 100, 1) if run.status == "done" else None,
            "citation_compliance": round((run.citation_compliance or 0) * 100, 1) if run.status == "done" else None,
        })




class QualityHumanRatingUpdateView(StaffRequiredMixin, View):
    def post(self, request, result_id: int):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

        try:
            res = EvalResult.objects.select_related("run", "item").get(id=result_id)
        except EvalResult.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Result not found"}, status=404)

        def norm(v):
            if v in (None, "", "null"):
                return None
            v = int(v)
            if v not in (0, 1, 2):
                raise ValueError("rating must be 0, 1, or 2")
            return v

        try:
            correctness = norm(payload.get("correctness"))
            completeness = norm(payload.get("completeness"))
            citations = norm(payload.get("citations"))

            HumanRating.objects.update_or_create(
                run=res.run,
                item=res.item,
                rater=request.user,
                defaults={
                    "correctness": correctness,
                    "completeness": completeness,
                    "citations": citations,
                },
            )
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

        return JsonResponse({"ok": True})

