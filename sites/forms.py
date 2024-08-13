from django import forms
from sites.models import Site


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ('name', 'url')

    def clean_name(self):
        name = self.cleaned_data['name']
        return name.replace(' ', '-')
