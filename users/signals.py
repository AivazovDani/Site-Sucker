from .models import Profile
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=User) # listening to when a user is created
def createProfile(sender, instance, created, **kwargs):
    if created:
        user = instance
        profile = Profile.objects.create(
            user = user,
            username = user.username,
            email = user.email,
        )



@receiver(post_delete, sender=Profile)
def deleteProfile(sender, instance, **kwargs):
    try:
        user = instance.user
        user.delete()
    except:

        pass


@receiver(post_save, sender=Profile)
def updateUser(sender, instance, created, **kwargs):
    if created:
        profile = instance
        user = profile.user

        if created == False:
            user.first_name = profile.username
            user.email = profile.email
            user.save()