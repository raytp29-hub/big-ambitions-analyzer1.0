description = "John Smith (McDonald's Daily Wage)"


parts = description.split("(")[0].strip()

print(parts)


business =  description.split("(")[1].split("Daily")[0].strip()
print(business)


# Replecement

replecement = "Replacement for Everett Beshears (Tech & Gift Wage)"


name = replecement.split("for")[-1].split("(")[0].strip()
print(name, "\n Nome del dipendente")


business = replecement.split("(")[-1].split("Wage")[0].strip()

print(business,"\n business name replecement")



# Marketing

marketing = "Marketing campaigns for G&J,123 as"

business_name = marketing.split("for")[-1].strip()

print(business_name)  # Dovrebbe stampare "G&J"




# Test 1: Health Insurance
desc1 = "Silver Health Insurance (Joseph Halliday) - 10 Employees"
employee_name = desc1.split("(")[1].split(")")[0].strip()
print(employee_name,"\n Nome del dipendente Health Insurance")

# Test 2: HR Training
desc2 = "Randy Haugen training costs"
nome_train = desc2.split("training")[0].strip()   # Dovrebbe dare "Randy Haugen"
print(nome_train, "\n Nome per HR training")