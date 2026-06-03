from django.forms import ModelForm
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Profile




class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['first_name', 'username', 'email', 'password1', 'password2']

    labels = {
        'first_name': 'Name'
    }


    def __init__(self, *args, **kwargs): # for styling
        super(RegisterForm, self).__init__(*args, **kwargs)

        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'input'})


class EditAccount(ModelForm):
    class Meta:
        model = Profile
        fields = ['username', 'email', 'image_profile']

    def __init__(self, *args, **kwargs): # for styling
        super(EditAccount, self).__init__(*args, **kwargs)

        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'input'})