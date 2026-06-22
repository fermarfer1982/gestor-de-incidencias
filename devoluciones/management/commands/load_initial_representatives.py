from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from core.access import ROLE_ALMACEN, ROLE_ADMINISTRACION, ROLE_COMERCIAL
from core.models import UserAccessProfile, UserRepresentativeScope
from devoluciones.models import Representative, UserRepresentative

REPRESENTATIVES = [
    ("4", "EDUARDO DIAZ IBAÑEZ"),
    ("8", "JOAQUIN GONZALEZ"),
    ("10", "BRUNO ESTEVAO"),
    ("15", "JOSE ANTONIO MARQUEZ ALMENDRO"),
    ("18", "JUAN VICENTE CUBILLOS PERIÑA"),
    ("59", "ALMERIA"),
    ("60", "MURCIA"),
    ("61", "SEVILLA"),
]

USER_REPRESENTATIVE_MAP = {
    "eduardo.diaz@ramiroarnedo.com": "4",
    "joaquin.gonzalez@ramiroarnedo.com": "8",
    "bruno.estevao@ramiroarnedo.com": "10",
    "jamarquez@ramiroarnedo.com": "15",
    "jvcubillos@ramiroarnedo.com": "18",
    "pgp@ramiroarnedo.com": "59",
    "jbervel@ramiroarnedo.com": "59",
    "antonio.cortes@ramiroarnedo.com": "59",
    "palomo@ramiroarnedo.com": "59",
    "antonio.zafra@ramiroarnedo.com": "59",
    "almeria@ramiroarnedo.com": "59",
    "ijj@ramiroarnedo.com": "59",
    "rsa@ramiroarnedo.com": "60",
    "javier.nicolas@ramiroarnedo.com": "60",
    "jbayano@ramiroarnedo.com": "60",
    "murcia@ramiroarnedo.com": "60",
    "enrique.cortines@ramiroarnedo.com": "61",
    "sevilla@ramiroarnedo.com": "61",
}


class Command(BaseCommand):
    help = "Carga representantes iniciales y relaciones usuario-representante."

    @transaction.atomic
    def handle(self, *args, **options):
        user_model = get_user_model()

        representative_created = 0
        representative_updated = 0
        user_created = 0
        user_updated = 0
        relationship_created = 0
        relationship_updated = 0
        groups_created = 0
        profiles_created = 0
        profiles_updated = 0
        scopes_created = 0
        scopes_updated = 0

        groups = {}
        for group_name in [ROLE_COMERCIAL, ROLE_ADMINISTRACION, ROLE_ALMACEN]:
            group, created = Group.objects.get_or_create(name=group_name)
            groups[group_name] = group
            if created:
                groups_created += 1

        representatives_by_code = {}
        for code, name in REPRESENTATIVES:
            representative, created = Representative.objects.update_or_create(
                code=code,
                defaults={"name": name},
            )
            representatives_by_code[code] = representative
            if created:
                representative_created += 1
            else:
                representative_updated += 1

        for email, representative_code in USER_REPRESENTATIVE_MAP.items():
            representative = representatives_by_code[representative_code]
            user = user_model.objects.filter(email__iexact=email).first()
            created = False
            if user is None:
                user = user_model.objects.create_user(
                    username=email,
                    email=email,
                )
                created = True
            else:
                fields_to_update = []
                if user.email != email:
                    user.email = email
                    fields_to_update.append("email")
                if not user.username:
                    user.username = email
                    fields_to_update.append("username")
                if fields_to_update:
                    user.save(update_fields=fields_to_update)

            if created:
                user_created += 1
            else:
                user_updated += 1

            user.groups.add(groups[ROLE_COMERCIAL])

            relationship, relationship_was_created = UserRepresentative.objects.update_or_create(
                user=user,
                defaults={
                    "representative": representative,
                    "active": True,
                },
            )
            if relationship_was_created:
                relationship_created += 1
            else:
                relationship_updated += 1

            profile, profile_was_created = UserAccessProfile.objects.update_or_create(
                user=user,
                defaults={
                    "role": ROLE_COMERCIAL,
                    "all_representatives": False,
                    "active": True,
                },
            )
            if profile_was_created:
                profiles_created += 1
            else:
                profiles_updated += 1

            scope, scope_was_created = UserRepresentativeScope.objects.update_or_create(
                profile=profile,
                representative=representative,
                defaults={"active": True},
            )
            if scope_was_created:
                scopes_created += 1
            else:
                scopes_updated += 1

        self.stdout.write(self.style.SUCCESS("Carga de datos iniciales completada."))
        self.stdout.write(
            "\n".join(
                [
                    f"Representantes creados: {representative_created}",
                    f"Representantes actualizados: {representative_updated}",
                    f"Usuarios creados: {user_created}",
                    f"Usuarios actualizados: {user_updated}",
                    f"Relaciones creadas: {relationship_created}",
                    f"Relaciones actualizadas: {relationship_updated}",
                    f"Grupos creados: {groups_created}",
                    f"Perfiles creados: {profiles_created}",
                    f"Perfiles actualizados: {profiles_updated}",
                    f"Alcances creados: {scopes_created}",
                    f"Alcances actualizados: {scopes_updated}",
                    f"Total representantes: {Representative.objects.count()}",
                    f"Total relaciones activas: {UserRepresentative.objects.filter(active=True).count()}",
                ]
            )
        )
