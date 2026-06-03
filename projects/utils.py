from anthropic import RateLimitError
import time
from django.db.models import Q
from.models import Projects
from django.core.paginator import Paginator


def call_api_with_retry(model, system, content, client): # our threads exceed the token limit for a api call to claude 
            max_retires = 5 # amaount of retires we will do


            for attemp in range(max_retires):
                try:
                    return client.messages.create( # creating the client
                        
                        model=model,
                        max_tokens=8096,
                        system=system,
                        messages=[{'role': 'user', 'content': content}]
                    )
                

                except RateLimitError:
                    wait = 2 ** attemp # 2^n
                    print(f'Rate limit hit, retrying in {wait}s...')
                    time.sleep(wait)
            raise Exception('Max retries exceeded')


def searchProjects(request):
    search_query = ''

    if request.GET.get('search_query'):
        search_query = request.GET.get('search_query')

    projects = Projects.objects.distinct().filter(Q(owner__username__icontains=search_query))
    
    return search_query, projects


def pagination(request, queryset):

    page = request.GET.get('page')
    
    p = Paginator(queryset, 5)

    return p.get_page(page)