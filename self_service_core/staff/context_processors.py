from .models import CompanyProfile

def company_context(request):
    """
    Stellt 'company' global in allen Templates bereit.
    """
    try:
        company = CompanyProfile.get_solo()
    except:
        company = None

    return {
        "company": company
    }
