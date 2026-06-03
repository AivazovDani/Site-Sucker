from django.forms import ModelForm
from django import forms
from .models import Projects

class ProjectForm(ModelForm):
    class Meta:
        model = Projects
        fields = ['title', 'decription', 'website_link']

    def __init__(self, *args, **kwargs):
        super(ProjectForm, self).__init__(*args, **kwargs)

        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'input'})