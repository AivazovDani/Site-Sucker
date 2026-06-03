from django.shortcuts import render, redirect
from .models import Projects
from .forms import ProjectForm
from .tasks import scrape
from django.contrib.auth.decorators import login_required
from .utils import pagination, searchProjects

# Create your views here.
def projects(request):
    projects = Projects.objects.all()
    profile = request.user.profile
    search_query, projects = searchProjects(request)
    p = pagination(request, projects)

    return render(request, 'projects/projects.html', {'projects': p, 'profile': profile, 'search_query': search_query, 'p': p})

def project(request, pk):
    project = Projects.objects.get(id=pk)


    return render(request, 'projects/project.html', {'project': project})

@login_required(login_url='login')
def createProject(request):

    form = ProjectForm()

    if request.method == 'POST':
        form = ProjectForm(request.POST)

        if form.is_valid():
            project = form.save(commit=False)
            
            project.owner = request.user.profile
            project.status = 'pending'

            project.save()
            project_id = project.id
            
            scrape.delay(project_id=project_id)
            
            return redirect('projects')
        
    return render(request, 'projects/create-porject.html', {'form': form})



@login_required(login_url='login')
def delete_project(request, pk):
    profile = request.user.profile
    project = profile.projects.get(id=pk)

    if request.method == 'POST':
        project.delete()
        

        return redirect('user-account')

    return render(request, 'projects/delete-project.html', {'project': project})


@login_required(login_url='login')
def edit_project(request, pk):
    profile = request.user.profile
    project = profile.projects.get(id=pk)
    form = ProjectForm(instance=project)

    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)


        if form.is_valid():
            form.save()
            return redirect('project', pk=project.id)
        
    return render(request, 'projects/edit-project.html', {'form': form, 'project': project})