from django import forms
from django.core.exceptions import ValidationError

from sites.models import Site


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ('name', 'url')

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(SiteForm, self).__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data['name']
        name = name.replace(' ', '-')

        if self.user and Site.objects.filter(user=self.user, name=name).exists():
            raise ValidationError("Сайт з такою назвою вже існує. Будь ласка, виберіть іншу назву.")

        return name
